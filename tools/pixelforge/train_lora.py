"""
PixelForge LoRA Training — pixelflow 보드 스타일 학습
=====================================================
SD 1.5 + 250장 pixelflow 보드로 LoRA fine-tuning.
RTX 3060 Ti 8GB에서 ~30-60분 소요.

사용법:
  python train_lora.py
  python train_lora.py --steps 2000 --lr 1e-4 --rank 8
"""

import argparse
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TRAIN_DIR = SCRIPT_DIR / "train_data"
OUTPUT_DIR = SCRIPT_DIR / "loras"
CACHE_DIR = Path("E:/AI/sd_models")

os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE_DIR / "hub")
os.environ["TORCH_HOME"] = str(CACHE_DIR / "torch")


def train(steps: int = 1500, lr: float = 1e-4, rank: int = 8,
          batch_size: int = 1, grad_accum: int = 4,
          resolution: int = 512, save_every: int = 500):
    """diffusers train_text_to_image_lora 기반 학습."""
    import subprocess

    output_path = OUTPUT_DIR / "pixelflow_board_lora"
    output_path.mkdir(parents=True, exist_ok=True)

    # diffusers 내장 학습 스크립트 사용
    cmd = [
        sys.executable, "-m", "accelerate", "launch",
        "--mixed_precision=fp16",
        "--num_processes=1",
        str(Path(sys.modules['diffusers'].__file__).parent.parent
            / "examples" / "text_to_image" / "train_text_to_image_lora.py"),

        f"--pretrained_model_name_or_path=runwayml/stable-diffusion-v1-5",
        f"--train_data_dir={TRAIN_DIR}",
        f"--output_dir={output_path}",
        f"--cache_dir={CACHE_DIR}",
        f"--resolution={resolution}",
        f"--train_batch_size={batch_size}",
        f"--gradient_accumulation_steps={grad_accum}",
        f"--max_train_steps={steps}",
        f"--learning_rate={lr}",
        f"--rank={rank}",
        "--lr_scheduler=cosine",
        "--lr_warmup_steps=100",
        f"--checkpointing_steps={save_every}",
        "--seed=42",
        "--enable_xformers_memory_efficient_attention",
        "--mixed_precision=fp16",
        "--dataloader_num_workers=0",
    ]

    print(f"[LoRA Train] Starting training...")
    print(f"  Steps: {steps}, LR: {lr}, Rank: {rank}")
    print(f"  Batch: {batch_size} x {grad_accum} accum = {batch_size * grad_accum} effective")
    print(f"  Data: {TRAIN_DIR} ({len(list(TRAIN_DIR.glob('*.png')))} images)")
    print(f"  Output: {output_path}")
    print(f"  Command: {' '.join(cmd[:5])} ...")
    print()

    result = subprocess.run(cmd, capture_output=False)
    if result.returncode == 0:
        print(f"\n[LoRA Train] Done! Model saved to {output_path}")
    else:
        print(f"\n[LoRA Train] Failed with code {result.returncode}")

    return output_path


def train_simple(steps: int = 1500, lr: float = 1e-4, rank: int = 4,
                 batch_size: int = 1, resolution: int = 512):
    """직접 구현 — diffusers examples 없이도 동작하는 간단한 LoRA 학습."""
    import torch
    from torch.utils.data import Dataset, DataLoader
    from diffusers import AutoencoderKL, UNet2DConditionModel, DDPMScheduler
    from transformers import CLIPTextModel, CLIPTokenizer
    from peft import LoraConfig, get_peft_model
    from PIL import Image
    import numpy as np
    from torchvision import transforms

    device = "cuda"
    dtype = torch.float16

    print(f"[LoRA Train] Loading models...")

    # 모델 로드
    tokenizer = CLIPTokenizer.from_pretrained(
        "runwayml/stable-diffusion-v1-5", subfolder="tokenizer", cache_dir=str(CACHE_DIR))
    text_encoder = CLIPTextModel.from_pretrained(
        "runwayml/stable-diffusion-v1-5", subfolder="text_encoder",
        cache_dir=str(CACHE_DIR), torch_dtype=dtype).to(device)
    vae = AutoencoderKL.from_pretrained(
        "runwayml/stable-diffusion-v1-5", subfolder="vae",
        cache_dir=str(CACHE_DIR), torch_dtype=dtype).to(device)
    unet = UNet2DConditionModel.from_pretrained(
        "runwayml/stable-diffusion-v1-5", subfolder="unet",
        cache_dir=str(CACHE_DIR), torch_dtype=dtype).to(device)
    scheduler = DDPMScheduler.from_pretrained(
        "runwayml/stable-diffusion-v1-5", subfolder="scheduler", cache_dir=str(CACHE_DIR))

    # Freeze all, add LoRA to UNet
    text_encoder.requires_grad_(False)
    vae.requires_grad_(False)
    unet.requires_grad_(False)

    lora_config = LoraConfig(
        r=rank,
        lora_alpha=rank,
        target_modules=["to_q", "to_k", "to_v", "to_out.0"],
        lora_dropout=0.05,
    )
    unet = get_peft_model(unet, lora_config)
    unet.print_trainable_parameters()

    # 학습 가능한 파라미터만 float32로
    for name, param in unet.named_parameters():
        if param.requires_grad:
            param.data = param.data.float()

    # Dataset
    class BoardDataset(Dataset):
        def __init__(self, data_dir, tokenizer, resolution):
            self.images = sorted(Path(data_dir).glob("*.png"))
            self.tokenizer = tokenizer
            self.transform = transforms.Compose([
                transforms.Resize(resolution, interpolation=transforms.InterpolationMode.LANCZOS),
                transforms.CenterCrop(resolution),
                transforms.ToTensor(),
                transforms.Normalize([0.5], [0.5]),
            ])

        def __len__(self):
            return len(self.images)

        def __getitem__(self, idx):
            img_path = self.images[idx]
            img = Image.open(img_path).convert("RGB")
            pixel_values = self.transform(img)

            # 캡션 로드
            caption_path = img_path.with_suffix(".txt")
            if caption_path.exists():
                caption = caption_path.read_text(encoding="utf-8").strip()
            else:
                caption = "pixel art cell board, colorful block grid, pixelflow board"

            tokens = self.tokenizer(
                caption, padding="max_length", truncation=True,
                max_length=77, return_tensors="pt")

            return {
                "pixel_values": pixel_values,
                "input_ids": tokens.input_ids.squeeze(0),
            }

    dataset = BoardDataset(TRAIN_DIR, tokenizer, resolution)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=0)

    # Optimizer
    optimizer = torch.optim.AdamW(
        [p for p in unet.parameters() if p.requires_grad],
        lr=lr, weight_decay=1e-2)

    # 학습 루프
    print(f"[LoRA Train] Starting: {steps} steps, {len(dataset)} images, rank={rank}")
    unet.train()
    step = 0
    losses = []

    while step < steps:
        for batch in dataloader:
            if step >= steps:
                break

            pixel_values = batch["pixel_values"].to(device, dtype=dtype)
            input_ids = batch["input_ids"].to(device)

            # VAE encode
            with torch.no_grad():
                latents = vae.encode(pixel_values).latent_dist.sample() * 0.18215

            # Text encode
            with torch.no_grad():
                encoder_hidden_states = text_encoder(input_ids)[0]

            # Noise
            noise = torch.randn_like(latents)
            timesteps = torch.randint(0, scheduler.config.num_train_timesteps,
                                      (latents.shape[0],), device=device).long()
            noisy_latents = scheduler.add_noise(latents, noise, timesteps)

            # UNet forward (mixed precision)
            with torch.autocast(device_type="cuda", dtype=dtype):
                noise_pred = unet(noisy_latents, timesteps, encoder_hidden_states).sample

            # Loss
            loss = torch.nn.functional.mse_loss(noise_pred.float(), noise.float())
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()

            losses.append(loss.item())
            step += 1

            if step % 100 == 0:
                avg_loss = sum(losses[-100:]) / min(100, len(losses))
                print(f"  Step {step}/{steps}, loss={avg_loss:.4f}")

            if step % 500 == 0:
                # 중간 저장
                save_path = OUTPUT_DIR / f"pixelflow_lora_step{step}"
                save_path.mkdir(parents=True, exist_ok=True)
                unet.save_pretrained(save_path)
                print(f"  Checkpoint saved: {save_path}")

    # 최종 저장
    save_path = OUTPUT_DIR / "pixelflow_lora_final"
    save_path.mkdir(parents=True, exist_ok=True)
    unet.save_pretrained(save_path)
    print(f"\n[LoRA Train] Done! Final model: {save_path}")
    print(f"  Average loss: {sum(losses) / len(losses):.4f}")

    return save_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=1500)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--rank", type=int, default=4)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--resolution", type=int, default=512)
    args = p.parse_args()

    train_simple(steps=args.steps, lr=args.lr, rank=args.rank,
                 batch_size=args.batch, resolution=args.resolution)


if __name__ == "__main__":
    main()

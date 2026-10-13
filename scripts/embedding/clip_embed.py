# -*- coding: utf-8 -*-
"""이미지 매니페스트 → CLIP ViT-B-32(laion2b_s34b_b79k, 512d) 벡터 JSONL (art_vectors 규약).
id = uuid5(6ba7b810-9dad-11d1-80b4-00c04fd430c8, "<project>|<path>"), payload = {project, path, name, kind}
RGBA/LA/P 이미지는 회색(128) 배경에 합성한 뒤 RGB 로 바꾼다.
2026-10-09 스크래치 clip_embed.py 를 승격(2026-10-12). 벡터 동작 동일, --threads/--batch 옵션만 추가.

사용 (CLIP 전용 venv):
  C:\\Users\\user\\clipenv\\Scripts\\python.exe scripts/embedding/clip_embed.py <manifest.jsonl> <out.jsonl> [--threads N] [--batch N]
  - 재실행 시 out 에 이미 있는 id 는 건너뛴다(이어하기).
  - 기본 threads = cpu-2, batch = 32. 다른 무거운 작업과 겹치면 --threads 4 정도로 낮춘다.
  - 결과 out.jsonl 은 임베딩컴으로 scp 후 host/artload_file.py 로 업서트.
"""
import os, sys, json, uuid, time, argparse
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
if os.path.isdir("E:/hf_cache"): os.environ.setdefault("HF_HOME", "E:/hf_cache")
ap = argparse.ArgumentParser()
ap.add_argument("manifest"); ap.add_argument("out")
ap.add_argument("--threads", type=int, default=max(2, (os.cpu_count() or 4) - 2))
ap.add_argument("--batch", type=int, default=32)
a = ap.parse_args()
import torch, open_clip
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
MANIFEST, OUT, BATCH = a.manifest, a.out, a.batch
torch.set_num_threads(a.threads)
done = set()
if os.path.exists(OUT):
    for l in open(OUT, encoding="utf-8"):
        try: done.add(json.loads(l)["id"])
        except Exception: pass
rows = [json.loads(l) for l in open(MANIFEST, encoding="utf-8") if l.strip()]
todo = [r for r in rows if str(uuid.uuid5(NS, r["project"] + "|" + r["path"])) not in done]
print(f"manifest {len(rows)} / already {len(done)} / todo {len(todo)} / threads {a.threads} batch {BATCH}", flush=True)
if not todo:
    print("=== done: wrote 0, decode failures 0, total 0s ===", flush=True); sys.exit(0)
model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k")
model.eval()
def load(p):
    im = Image.open(p)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA"); bg = Image.new("RGBA", im.size, (128, 128, 128, 255)); im = Image.alpha_composite(bg, im)
    return im.convert("RGB")
out = open(OUT, "a", encoding="utf-8"); n = 0; bad = 0; t0 = time.time()
with torch.no_grad():
    for i in range(0, len(todo), BATCH):
        b = todo[i:i + BATCH]; imgs = []; keep = []
        for r in b:
            try: imgs.append(preprocess(load(r["path"]))); keep.append(r)
            except Exception as e:
                bad += 1; print("  decode fail:", r["path"], str(e)[:80], flush=True)
        if not imgs: continue
        feats = model.encode_image(torch.stack(imgs)); feats = feats / feats.norm(dim=-1, keepdim=True)
        for r, v in zip(keep, feats.tolist()):
            out.write(json.dumps({"id": str(uuid.uuid5(NS, r["project"] + "|" + r["path"])), "vector": v, "payload": {"project": r["project"], "path": r["path"], "name": r["name"], "kind": r["kind"]}}) + "\n")
            n += 1
        out.flush()
        if (i // BATCH) % 20 == 0: print(f"  {n}/{len(todo)} bad={bad} {time.time()-t0:.0f}s", flush=True)
print(f"=== done: wrote {n}, decode failures {bad}, total {time.time()-t0:.0f}s ===", flush=True)

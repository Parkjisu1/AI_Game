"""
YOLO 학습 데이터셋 준비
1. 다양한 레벨의 이미지 선택
2. 자동 라벨링
3. train/val 분할
"""
import os, sys, shutil, random
from auto_label import auto_label, CLASSES

SRC_DIR = r"E:\AI\virtual_player\data\pixelflow\images"
DST_DIR = r"E:\AI\virtual_player\yolo\pixelflow\dataset"

# 다양한 시점의 이미지 선택 (before = 레벨 시작 상태)
SAMPLE_INDICES = [
    1, 14, 44, 50, 100, 150, 200, 300, 400, 500,
    600, 700, 800, 900, 1000, 1500, 2000, 3000, 5000, 7000, 10000
]

def find_images():
    """다양한 인덱스의 before/after 이미지 수집"""
    all_files = sorted(os.listdir(SRC_DIR))
    selected = []

    for idx in SAMPLE_INDICES:
        # before와 after 모두 찾기
        suffix_before = f"_{idx:04d}_before.png"
        suffix_after = f"_{idx:04d}_after.png"
        for f in all_files:
            if f.endswith(suffix_before) or f.endswith(suffix_after):
                selected.append(f)

    # 중복 제거
    return sorted(set(selected))


def main():
    images = find_images()
    print(f"Selected {len(images)} images")

    # 80/20 train/val split
    random.seed(42)
    random.shuffle(images)
    split = int(len(images) * 0.8)
    train_imgs = images[:split]
    val_imgs = images[split:]

    print(f"Train: {len(train_imgs)}, Val: {len(val_imgs)}")

    total_labels = 0
    for split_name, img_list in [('train', train_imgs), ('val', val_imgs)]:
        img_dir = os.path.join(DST_DIR, 'images', split_name)
        lbl_dir = os.path.join(DST_DIR, 'labels', split_name)
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(lbl_dir, exist_ok=True)

        for fname in img_list:
            src_path = os.path.join(SRC_DIR, fname)
            dst_img = os.path.join(img_dir, fname)

            # 이미지 복사
            shutil.copy2(src_path, dst_img)

            # 자동 라벨링
            labels = auto_label(src_path, lbl_dir)
            total_labels += len(labels)

            from collections import Counter
            cnt = Counter(CLASSES[l[0]] for l in labels)
            summary = ', '.join(f"{k.replace('block_','')}:{v}" for k, v in cnt.most_common(3))
            print(f"  [{split_name}] {fname}: {len(labels)} labels ({summary})")

    print(f"\nTotal: {total_labels} labels across {len(images)} images")

    # YOLO config 생성
    config_path = os.path.join(DST_DIR, 'dataset.yaml')
    with open(config_path, 'w') as f:
        f.write(f"path: {DST_DIR}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(CLASSES)}\n")
        f.write(f"names: {CLASSES}\n")
    print(f"\nSaved: {config_path}")


if __name__ == '__main__':
    main()

"""
레벨 시작 이미지 선택 — 각 레벨의 첫 before 이미지를 labeling 폴더에 복사
OCR 없이 인덱스 기반 샘플링 (약 300장)
"""
import os, shutil

SRC = r"E:\AI\virtual_player\data\pixelflow\images"
DST = r"E:\AI\virtual_player\yolo\pixelflow\labeling\images"

# before 이미지만 수집, 인덱스 순서로 정렬
all_files = sorted([f for f in os.listdir(SRC) if f.endswith('_before.png')])
print(f"Total before images: {len(all_files)}")

# 인덱스 추출
def get_index(fname):
    # click_20260325_101717_0001_before.png → 0001
    parts = fname.split('_')
    return int(parts[3])

# 레벨별 턴 수 추정 (관측 데이터 기반):
# Lv1: idx~1, Lv2: idx~14, Lv3: idx~44, Lv5: idx~107
# Lv8: idx~200, Lv15: idx~500, Lv20: idx~1000
# Lv59: idx~5000, Lv120: idx~10000, Lv216: idx~20000
#
# 전략: 구간별 다른 간격으로 샘플링
# idx 1-200: every 5 (초반 레벨 세밀히) → ~40장
# idx 200-1000: every 20 → ~40장
# idx 1000-5000: every 50 → ~80장
# idx 5000-15000: every 80 → ~125장
# idx 15000-33000: every 300 → ~60장
# 총 ~345장

samples = set()
# 초반 (Lv1-8)
for i in range(1, 200, 5):
    samples.add(i)
# 중반 (Lv8-20)
for i in range(200, 1000, 20):
    samples.add(i)
# 중후반 (Lv20-60)
for i in range(1000, 5000, 50):
    samples.add(i)
# 후반 (Lv60-150)
for i in range(5000, 15000, 80):
    samples.add(i)
# 고레벨 (Lv150-300+)
for i in range(15000, 33001, 300):
    samples.add(i)

print(f"Target indices: {len(samples)}")

# 가장 가까운 before 이미지 찾아서 복사
copied = 0
idx_map = {}
for f in all_files:
    idx = get_index(f)
    idx_map[idx] = f

sorted_indices = sorted(idx_map.keys())

selected = set()
for target in sorted(samples):
    # 가장 가까운 인덱스 찾기
    closest = min(sorted_indices, key=lambda x: abs(x - target))
    if closest not in selected and abs(closest - target) < 50:
        selected.add(closest)
        fname = idx_map[closest]
        # 레벨 번호는 모르니까 인덱스로 이름 지정
        dst_name = f"idx_{closest:05d}.png"
        shutil.copy2(os.path.join(SRC, fname), os.path.join(DST, dst_name))
        copied += 1

print(f"Copied: {copied} images to {DST}")

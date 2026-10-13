"""
Grid Dimension Auto-Detector v2 (FFT + Prior)
=============================================
FFT 주파수 분석 + 셀 크기 prior로 그리드 차원 탐지.

기존 autocorrelation 한계:
- 셀 내부 디테일 → sub-cell 피치 오탐지 (Level 200 케이스)
- 셀 alternating 패턴 → 2x 피치 오탐지 (Level 51 케이스)

개선:
1. Gaussian blur로 셀 내부 노이즈 제거
2. FFT magnitude spectrum 계산
3. 라벨 bbox 기반 prior (12~35px) 내에서 최강 peak 선택
4. Harmonic check: fundamental 우선
"""
from __future__ import annotations
import numpy as np
from typing import Optional


# 라벨 데이터 기반 prior (px 단위)
DEFAULT_PITCH_MIN = 12
DEFAULT_PITCH_MAX = 35


def _smooth_profile(profile: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """Gaussian smoothing으로 sub-cell 노이즈 제거."""
    if sigma <= 0:
        return profile
    # 1D Gaussian kernel
    radius = int(3 * sigma)
    x = np.arange(-radius, radius + 1)
    kernel = np.exp(-(x ** 2) / (2 * sigma ** 2))
    kernel = kernel / kernel.sum()
    # Reflect padding
    padded = np.pad(profile, radius, mode="reflect")
    return np.convolve(padded, kernel, mode="valid")


def _detect_pitch_fft(
    profile: np.ndarray,
    pitch_min: int = DEFAULT_PITCH_MIN,
    pitch_max: int = DEFAULT_PITCH_MAX,
) -> tuple[float, float, dict]:
    """FFT magnitude spectrum에서 최강 peak의 pitch 반환.

    Returns:
        (pitch, confidence, debug_info)
    """
    n = len(profile)
    if n < pitch_max * 2:
        return 30.0, 0.0, {"reason": "profile too short"}

    # Smoothing (Gaussian, sigma=2px)
    smoothed = _smooth_profile(profile, sigma=2.0)

    # DC 제거
    centered = smoothed - smoothed.mean()

    # FFT
    spectrum = np.abs(np.fft.rfft(centered))

    # 각 bin k의 주기: n / k (픽셀)
    # pitch_min ≤ n/k ≤ pitch_max
    # → n/pitch_max ≤ k ≤ n/pitch_min
    k_min = max(1, int(np.ceil(n / pitch_max)))
    k_max = min(len(spectrum) - 1, int(np.floor(n / pitch_min)))

    if k_min >= k_max:
        return 30.0, 0.0, {"reason": "prior range too narrow"}

    # prior 범위 내 강도
    range_mag = spectrum[k_min:k_max + 1]
    peak_idx_local = int(np.argmax(range_mag))
    peak_k = k_min + peak_idx_local
    peak_mag = range_mag[peak_idx_local]
    total_energy = np.sum(spectrum[1:])
    confidence = float(peak_mag / total_energy) if total_energy > 0 else 0.0

    pitch = float(n / peak_k)

    # Harmonic check: 2배 주파수(= pitch/2)에 강한 peak 있으면 현재가 fundamental
    # 반대로, 절반 주파수(= pitch*2)가 prior 내에 있고 더 강하면 그게 fundamental
    k_half = peak_k // 2
    if k_half >= k_min and k_half < len(spectrum):
        mag_half = spectrum[k_half]
        # 반-주파수 peak이 더 강하면 현재 peak은 harmonic
        if mag_half > peak_mag * 0.8:
            pitch = float(n / k_half)
            peak_k = k_half
            peak_mag = mag_half

    return pitch, confidence, {
        "peak_k": peak_k,
        "peak_magnitude": float(peak_mag),
        "total_energy": float(total_energy),
        "k_range": (k_min, k_max),
    }


def _find_gridlines(profile: np.ndarray, pitch: float) -> list[int]:
    """주어진 pitch로 gridline 위치 탐지 (phase sweep + 누적 drift 보정).

    개선:
      - float pitch 유지 (누적 정확도)
      - 각 gridline을 이전 gridline + pitch로 예측 후 로컬 최소값 보정
      - 보정된 위치로부터 다음 gridline 예측 (누적 drift 방지)
    """
    n = len(profile)
    if pitch < 3 or n < pitch * 2:
        return []
    pitch_int = max(3, int(round(pitch)))

    # 각 phase에서 grid 위치들의 총 밝기 최소 계산
    best_phase = 0
    best_score = float("inf")
    for phase in range(pitch_int):
        positions = list(range(phase, n, pitch_int))
        if len(positions) < 2:
            continue
        score = sum(
            float(np.min(profile[max(0, p - 2):min(n, p + 3)]))
            for p in positions
        ) / len(positions)
        if score < best_score:
            best_score = score
            best_phase = phase

    # gridline 위치 (이전 위치 + pitch로 예측 → 로컬 최소값 보정 → 다음 예측)
    gridlines: list[int] = []
    pos = float(best_phase)
    search_radius = max(3, int(pitch * 0.25))  # 로컬 검색 범위를 피치의 25%로
    while pos < n:
        lo = max(0, int(round(pos)) - search_radius)
        hi = min(n, int(round(pos)) + search_radius + 1)
        if hi <= lo:
            break
        # 로컬 최소값 찾기
        local_min = lo + int(np.argmin(profile[lo:hi]))
        gridlines.append(local_min)
        # 다음 gridline은 "보정된" 현재 위치 + pitch (누적 drift 방지)
        pos = local_min + pitch

    return gridlines


def _add_boundary_gridlines(gridlines: list[int], n: int) -> list[int]:
    """보드 edge 가상 gridline 추가."""
    if len(gridlines) < 2:
        return gridlines
    gridlines = sorted(set(gridlines))
    median_gap = int(np.median(np.diff(gridlines)))
    result = list(gridlines)
    if result[0] > median_gap * 0.5:
        result.insert(0, max(0, result[0] - median_gap))
    if n - result[-1] > median_gap * 0.5:
        result.append(min(n, result[-1] + median_gap))
    return result


def detect_grid_dimensions(
    board_rgb: np.ndarray,
    pitch_min: int = DEFAULT_PITCH_MIN,
    pitch_max: int = DEFAULT_PITCH_MAX,
    profile_mode: str = "luminance",
) -> dict:
    """FFT 기반 그리드 차원 탐지.

    Args:
        board_rgb: HxWx3 RGB (보드만 크롭됨)
        pitch_min/max: 셀 피치 prior 범위 (px)
        profile_mode: 'luminance' | 'edge'
    """
    h, w = board_rgb.shape[:2]

    if profile_mode == "edge":
        gray = np.mean(board_rgb[:, :, :3].astype(np.float64), axis=2)
        dx = np.abs(np.diff(gray, axis=1, prepend=gray[:, :1]))
        dy = np.abs(np.diff(gray, axis=0, prepend=gray[:1, :]))
        col_profile = dx.mean(axis=0)
        row_profile = dy.mean(axis=1)
    else:
        gray = np.mean(board_rgb[:, :, :3].astype(np.float64), axis=2)
        col_profile = gray.mean(axis=0)
        row_profile = gray.mean(axis=1)

    # FFT로 피치 탐지
    pitch_h, conf_h, dbg_h = _detect_pitch_fft(col_profile, pitch_min, pitch_max)
    pitch_v, conf_v, dbg_v = _detect_pitch_fft(row_profile, pitch_min, pitch_max)

    # gridline 위치 탐지
    gridlines_h = _find_gridlines(col_profile, pitch_h)
    gridlines_v = _find_gridlines(row_profile, pitch_v)

    # 경계 gridline 보완
    gridlines_h = _add_boundary_gridlines(gridlines_h, w)
    gridlines_v = _add_boundary_gridlines(gridlines_v, h)

    cols = max(0, len(gridlines_h) - 1)
    rows = max(0, len(gridlines_v) - 1)

    return {
        "rows": rows,
        "cols": cols,
        "pitch_h": pitch_h,
        "pitch_v": pitch_v,
        "gridlines_h": gridlines_h,
        "gridlines_v": gridlines_v,
        "confidence": float((conf_h + conf_v) / 2),
        "debug_h": dbg_h,
        "debug_v": dbg_v,
    }


def get_cell_bounds(result: dict, row: int, col: int) -> Optional[tuple[int, int, int, int]]:
    gh = result.get("gridlines_h", [])
    gv = result.get("gridlines_v", [])
    if col + 1 >= len(gh) or row + 1 >= len(gv):
        return None
    return gh[col], gv[row], gh[col + 1], gv[row + 1]


if __name__ == "__main__":
    import sys, cv2
    if len(sys.argv) < 2:
        print("Usage: python grid_detector.py <image>")
        sys.exit(1)

    img = cv2.imread(sys.argv[1])
    if img is None:
        print(f"Cannot read: {sys.argv[1]}")
        sys.exit(1)

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    r = detect_grid_dimensions(rgb)
    print(f"Image: {img.shape[1]}x{img.shape[0]}")
    print(f"Grid:  {r['cols']} x {r['rows']}")
    print(f"Pitch: {r['pitch_h']:.1f} x {r['pitch_v']:.1f} px")
    print(f"Conf:  {r['confidence']:.3f}")

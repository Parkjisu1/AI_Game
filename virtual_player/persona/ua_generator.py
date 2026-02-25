"""
User-Agent Generator
=====================
디바이스 프로필 기반 UA 문자열 생성.
Android Chrome, iOS Safari 등.
"""

import random
from typing import Optional

from .archetypes import DeviceProfile


# ============================================================
# UA Templates
# ============================================================

_CHROME_VERSIONS = [
    "120.0.6099.144",
    "121.0.6167.85",
    "122.0.6261.64",
    "123.0.6312.40",
    "124.0.6367.60",
]

_SAFARI_VERSIONS = ["17.2", "17.3", "17.4", "17.5"]

# Android OS versions paired with Chrome releases
_ANDROID_OS_VERSIONS = ["12", "13", "14"]

# iOS versions paired with Safari releases (major.minor format for UA string)
_IOS_OS_VERSIONS = ["16_6", "17_0", "17_2", "17_4"]


# ============================================================
# Generator
# ============================================================

def generate_user_agent(device: DeviceProfile) -> str:
    """
    디바이스 프로필에 맞는 UA 문자열 생성.

    Android  → Chrome Mobile UA
    iOS      → Safari Mobile UA (iPhone 또는 iPad)
    기타      → 범용 fallback UA

    Args:
        device: DeviceProfile 인스턴스.

    Returns:
        UA 문자열.
    """
    if device.os == "android":
        return _android_ua(device)
    elif device.os == "ios":
        return _ios_ua(device)
    else:
        return "Mozilla/5.0 (Unknown Device)"


# ============================================================
# Internal helpers
# ============================================================

def _android_ua(device: DeviceProfile) -> str:
    """Android Chrome Mobile UA 생성."""
    chrome_ver = random.choice(_CHROME_VERSIONS)
    android_ver = random.choice(_ANDROID_OS_VERSIONS)

    # Galaxy 기기는 모델명 인코딩 없이 원문 그대로 사용 (실제 UA 관례)
    model = device.name

    return (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_ver} Mobile Safari/537.36"
    )


def _ios_ua(device: DeviceProfile) -> str:
    """iOS Safari Mobile UA 생성."""
    safari_ver = random.choice(_SAFARI_VERSIONS)
    ios_ver = random.choice(_IOS_OS_VERSIONS)
    webkit_ver = "605.1.15"

    # iPad는 별도 플랫폼 토큰 사용
    is_ipad = "ipad" in device.name.lower()
    if is_ipad:
        platform_token = f"iPad; CPU OS {ios_ver} like Mac OS X"
    else:
        platform_token = f"iPhone; CPU iPhone OS {ios_ver} like Mac OS X"

    return (
        f"Mozilla/5.0 ({platform_token}) "
        f"AppleWebKit/{webkit_ver} (KHTML, like Gecko) "
        f"Version/{safari_ver} Mobile/15E148 Safari/604.1"
    )

"""
Persona Archetypes
===================
5종 가상 플레이어 프리셋 + Skill/DeviceProfile 정의.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import DEVICES_JSON


# ============================================================
# Data classes
# ============================================================

@dataclass
class Skill:
    """플레이어 숙련도."""
    reaction_time: float  # seconds (lower = better, range 0.15~2.0)
    accuracy: float       # 0.0~1.0 (tap/swipe precision)
    strategy: float       # 0.0~1.0 (optimal play probability)
    patience: float       # 0.0~1.0 (willingness to wait/grind)
    # BT decision parameters (used by PersonaGate nodes)
    risk_tolerance: float = 0.5    # 0=cautious, 1=aggressive
    explore_rate: float = 0.3      # 0=never explore, 1=always explore
    spend_threshold: float = 0.3   # 0=hoard, 1=spend freely


@dataclass
class DeviceProfile:
    """디바이스 정보."""
    name: str
    os: str            # "android" | "ios"
    width: int         # screen width px
    height: int        # screen height px
    dpi: int
    ram_gb: float
    year: int          # release year


@dataclass
class Persona:
    """가상 플레이어 페르소나."""
    name: str
    description: str
    skill: Skill
    preferred_session_minutes: Tuple[int, int]  # (min, max)
    pay_probability: float                       # 0.0~1.0
    preferred_devices: List[str]                 # device name filters
    metadata: Dict[str, Any] = field(default_factory=dict)

    def pick_device(self, devices: List[DeviceProfile]) -> DeviceProfile:
        """페르소나에 맞는 디바이스 랜덤 선택."""
        if self.preferred_devices:
            filtered = [
                d for d in devices
                if any(pref.lower() in d.name.lower() for pref in self.preferred_devices)
            ]
            if filtered:
                return random.choice(filtered)
        return random.choice(devices)


# ============================================================
# Preset archetypes
# ============================================================

ARCHETYPES: Dict[str, Persona] = {
    "casual": Persona(
        name="casual",
        description="라이트 유저. 짧은 세션, 낮은 과금 의향, 주로 중급 Android 기기 사용.",
        skill=Skill(
            reaction_time=0.8,
            accuracy=0.6,
            strategy=0.4,
            patience=0.3,
            risk_tolerance=0.3,
            explore_rate=0.2,
            spend_threshold=0.2,
        ),
        preferred_session_minutes=(5, 20),
        pay_probability=0.05,
        preferred_devices=["Galaxy", "Pixel"],
        metadata={"segment": "light", "ltv_tier": "low"},
    ),
    "hardcore": Persona(
        name="hardcore",
        description="하드코어 유저. 긴 세션, 높은 숙련도, 플래그십 기기 선호.",
        skill=Skill(
            reaction_time=0.25,
            accuracy=0.9,
            strategy=0.85,
            patience=0.8,
            risk_tolerance=0.8,
            explore_rate=0.5,
            spend_threshold=0.5,
        ),
        preferred_session_minutes=(30, 120),
        pay_probability=0.3,
        preferred_devices=["iPhone 15", "Galaxy S24"],
        metadata={"segment": "core", "ltv_tier": "high"},
    ),
    "whale": Persona(
        name="whale",
        description="고과금 유저. 중간 세션, 높은 과금 의향, 최상위 기기 사용.",
        skill=Skill(
            reaction_time=0.5,
            accuracy=0.7,
            strategy=0.6,
            patience=0.5,
            risk_tolerance=0.5,
            explore_rate=0.4,
            spend_threshold=0.95,
        ),
        preferred_session_minutes=(15, 60),
        pay_probability=0.9,
        preferred_devices=["iPhone 15 Pro", "Galaxy S24 Ultra"],
        metadata={"segment": "whale", "ltv_tier": "very_high"},
    ),
    "newbie": Persona(
        name="newbie",
        description="신규 유저. 짧은 세션, 낮은 숙련도, 기기 제한 없음.",
        skill=Skill(
            reaction_time=1.5,
            accuracy=0.3,
            strategy=0.15,
            patience=0.4,
            risk_tolerance=0.2,
            explore_rate=0.6,
            spend_threshold=0.1,
        ),
        preferred_session_minutes=(3, 15),
        pay_probability=0.02,
        preferred_devices=[],
        metadata={"segment": "new", "ltv_tier": "unknown"},
    ),
    "returning": Persona(
        name="returning",
        description="복귀 유저. 중간 세션, 중간 숙련도, 주요 Android/iOS 기기 사용.",
        skill=Skill(
            reaction_time=0.6,
            accuracy=0.5,
            strategy=0.5,
            patience=0.35,
            risk_tolerance=0.4,
            explore_rate=0.3,
            spend_threshold=0.3,
        ),
        preferred_session_minutes=(10, 30),
        pay_probability=0.1,
        preferred_devices=["Galaxy", "iPhone"],
        metadata={"segment": "returning", "ltv_tier": "medium"},
    ),
}


# ============================================================
# Utility functions
# ============================================================

def get_persona(name: str) -> Persona:
    """
    이름으로 프리셋 페르소나를 반환.

    Args:
        name: ARCHETYPES의 키 (casual/hardcore/whale/newbie/returning).

    Returns:
        Persona 인스턴스.

    Raises:
        KeyError: 알 수 없는 페르소나 이름.
    """
    if name not in ARCHETYPES:
        valid = ", ".join(ARCHETYPES.keys())
        raise KeyError(f"Unknown persona '{name}'. Valid options: {valid}")
    return ARCHETYPES[name]


def load_devices(path: Optional[Path] = None) -> List[DeviceProfile]:
    """
    devices.json 파일에서 DeviceProfile 목록을 로드.

    Args:
        path: devices.json 경로. None이면 config.DEVICES_JSON 사용.

    Returns:
        DeviceProfile 인스턴스 목록.

    Raises:
        FileNotFoundError: 파일을 찾을 수 없을 때.
        ValueError: JSON 형식이 올바르지 않을 때.
    """
    target = Path(path) if path is not None else DEVICES_JSON

    if not target.exists():
        raise FileNotFoundError(f"devices.json not found at: {target}")

    with target.open("r", encoding="utf-8") as fp:
        raw: List[Dict[str, Any]] = json.load(fp)

    profiles: List[DeviceProfile] = []
    for entry in raw:
        try:
            profiles.append(
                DeviceProfile(
                    name=entry["name"],
                    os=entry["os"],
                    width=int(entry["width"]),
                    height=int(entry["height"]),
                    dpi=int(entry["dpi"]),
                    ram_gb=float(entry["ram_gb"]),
                    year=int(entry["year"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid device entry {entry!r}: {exc}") from exc

    return profiles

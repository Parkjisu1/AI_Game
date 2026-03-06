"""Combat controller: skill rotation, HP management during battle."""
from __future__ import annotations
import logging
import time
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Callable, Dict

logger = logging.getLogger(__name__)


@dataclass
class SkillSlot:
    """A skill button on the battle screen."""
    name: str
    x: int                          # screen x coordinate
    y: int                          # screen y coordinate
    cooldown_s: float = 10.0        # cooldown duration in seconds
    priority: int = 1               # higher = use first (heal=10, buff=5, dps=1)
    skill_type: str = "dps"         # dps, heal, buff, debuff, ultimate
    icon_region: tuple = field(default_factory=tuple)  # (x, y, w, h) for brightness check

    def __post_init__(self):
        if not self.icon_region:
            # Default: 40x40 region centered on skill button
            self.icon_region = (self.x - 20, self.y - 20, 40, 40)


class CombatController:
    """Manages skill usage during battle screens."""

    BRIGHTNESS_READY_THRESHOLD = 100   # pixel brightness above this = skill ready
    HP_CRITICAL = 0.3                   # use heal skill below this
    HP_EMERGENCY = 0.15                 # emergency: use any heal available

    def __init__(self, skill_slots: List[SkillSlot], input_fn: Callable,
                 gauge_reader=None):
        """
        Args:
            skill_slots: List of skill buttons configured for this game
            input_fn: callable(x, y) to tap screen coordinates
            gauge_reader: GaugeReader instance for HP/MP reading
        """
        self._skills = sorted(skill_slots, key=lambda s: -s.priority)
        self._input_fn = input_fn
        self._gauge_reader = gauge_reader
        self._last_used: Dict[str, float] = {}  # skill_name -> timestamp
        self._rotation_idx: int = 0              # round-robin for DPS skills

    def tick(self, screenshot_path: str, game_state: Optional[dict] = None) -> Optional[str]:
        """
        Make one combat decision based on current battle state.

        Returns description of action taken, or None if no action needed.
        """
        img = cv2.imread(str(screenshot_path))
        if img is None:
            return None

        # Get HP from game_state or gauge_reader
        hp_pct = 1.0
        mp_pct = 1.0
        if game_state:
            hp_pct = game_state.get('hp_pct', 1.0) or 1.0
            mp_pct = game_state.get('mp_pct', 1.0) or 1.0

        now = time.time()

        # Priority 1: Emergency heal
        if hp_pct < self.HP_EMERGENCY:
            heal = self._find_ready_skill(img, now, skill_type="heal")
            if heal:
                return self._use_skill(heal, now, "emergency_heal")

        # Priority 2: Normal heal when HP low
        if hp_pct < self.HP_CRITICAL:
            heal = self._find_ready_skill(img, now, skill_type="heal")
            if heal:
                return self._use_skill(heal, now, "heal")

        # Priority 3: Buff skills (use when available)
        buff = self._find_ready_skill(img, now, skill_type="buff")
        if buff:
            return self._use_skill(buff, now, "buff")

        # Priority 4: Ultimate (use when available)
        ult = self._find_ready_skill(img, now, skill_type="ultimate")
        if ult:
            return self._use_skill(ult, now, "ultimate")

        # Priority 5: DPS rotation
        dps_skills = [s for s in self._skills if s.skill_type == "dps"]
        if dps_skills:
            # Round-robin through DPS skills
            for i in range(len(dps_skills)):
                idx = (self._rotation_idx + i) % len(dps_skills)
                skill = dps_skills[idx]
                if self._is_skill_ready(img, skill, now):
                    self._rotation_idx = (idx + 1) % len(dps_skills)
                    return self._use_skill(skill, now, "dps")

        return None  # No action needed (auto-attack handles it)

    def _find_ready_skill(self, img: np.ndarray, now: float,
                          skill_type: str) -> Optional[SkillSlot]:
        """Find first ready skill of given type."""
        for skill in self._skills:
            if skill.skill_type == skill_type and self._is_skill_ready(img, skill, now):
                return skill
        return None

    def _is_skill_ready(self, img: np.ndarray, skill: SkillSlot, now: float) -> bool:
        """Check if skill is off cooldown by checking icon brightness."""
        # Cooldown timer check
        last = self._last_used.get(skill.name, 0)
        if now - last < skill.cooldown_s:
            return False

        # Visual brightness check
        x, y, w, h = skill.icon_region
        # Clamp to image bounds
        h_img, w_img = img.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)

        if x2 <= x1 or y2 <= y1:
            return True  # Can't check, assume ready

        roi = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        avg_brightness = float(np.mean(gray))

        return avg_brightness >= self.BRIGHTNESS_READY_THRESHOLD

    def _use_skill(self, skill: SkillSlot, now: float, reason: str) -> str:
        """Tap a skill and record usage."""
        self._last_used[skill.name] = now
        self._input_fn(skill.x, skill.y)
        desc = f"combat:{reason}:{skill.name} at ({skill.x},{skill.y})"
        logger.info(desc)
        return desc

    @classmethod
    def from_profile(cls, profile: dict, input_fn: Callable,
                     gauge_reader=None) -> Optional['CombatController']:
        """Create CombatController from game profile YAML dict."""
        skill_data = profile.get('skill_slots', [])
        if not skill_data:
            return None

        slots = []
        for s in skill_data:
            slots.append(SkillSlot(
                name=s.get('name', 'skill'),
                x=s.get('x', 0),
                y=s.get('y', 0),
                cooldown_s=s.get('cooldown_s', 10.0),
                priority=s.get('priority', 1),
                skill_type=s.get('type', 'dps'),
            ))

        if not slots:
            return None

        return cls(slots, input_fn, gauge_reader)

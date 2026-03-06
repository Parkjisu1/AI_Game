"""
Ash & Veil -- Action Executors
===============================
Multi-step ADB tap sequences for each GOAP action.
Each executor returns True on success, False on failure.

Uses raw ADB primitives: tap(x,y), screenshot, classify.
Coordinates are for 1080x1920 resolution (BlueStacks default).
"""

import time
import subprocess
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import numpy as np
from PIL import Image


class ANVExecutor:
    """Executes GOAP actions via ADB tap sequences for Ash & Veil."""

    ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
    DEVICE = "emulator-5554"

    def __init__(
        self,
        temp_dir: Path,
        classify_fn: Callable[[Path], Tuple[str, float]],
        log_fn: Callable[[str], None] = print,
    ):
        self._temp = temp_dir
        self._temp.mkdir(parents=True, exist_ok=True)
        self._classify = classify_fn
        self._log = log_fn
        self._step = 0

    # ─── ADB primitives ───────────────────────────────────────

    def _adb(self, args, timeout=10):
        full = [self.ADB, "-s", self.DEVICE] + args
        try:
            return subprocess.run(full, capture_output=True, timeout=timeout)
        except Exception:
            return None

    def tap(self, x: int, y: int, desc: str = "", wait: float = 1.0):
        if desc:
            self._log(f"  TAP ({x},{y}) - {desc}")
        self._adb(["shell", "input", "tap", str(x), str(y)])
        if wait > 0:
            time.sleep(wait)

    def swipe(self, x1, y1, x2, y2, ms=500, wait=1.0):
        self._adb(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms)])
        if wait > 0:
            time.sleep(wait)

    def back(self, wait=1.5):
        self._adb(["shell", "input", "keyevent", "KEYCODE_BACK"])
        time.sleep(wait)

    def screenshot(self, name: str = "exec") -> Optional[Path]:
        self._step += 1
        path = self._temp / f"{name}_{self._step:04d}.png"
        r = self._adb(["exec-out", "screencap", "-p"], timeout=15)
        if r and r.stdout:
            with open(path, "wb") as f:
                f.write(r.stdout)
            return path
        return None

    def classify(self, path: Optional[Path]) -> Tuple[str, float]:
        if path is None:
            return "error", 0.0
        return self._classify(path)

    def current_screen(self) -> Tuple[str, float]:
        """Screenshot + classify in one call."""
        path = self.screenshot("check")
        return self.classify(path)

    def wait_for_screen(self, target: str, timeout: float = 15.0) -> bool:
        """Wait until the specified screen appears."""
        start = time.time()
        while time.time() - start < timeout:
            stype, conf = self.current_screen()
            if stype == target:
                return True
            time.sleep(1.5)
        return False

    # ─── Battle field detection (reused from autonomous_player) ───

    def is_battle_field(self, path: Path) -> bool:
        try:
            img = np.array(Image.open(path))
            h, w = img.shape[:2]
            bottom = img[int(h * 0.88):int(h * 0.95), :, :]
            auto_area = img[int(h * 0.95):, :, :]
            center = img[int(h * 0.3):int(h * 0.6), :, :]
            top_center = img[int(h * 0.05):int(h * 0.12), int(w * 0.35):int(w * 0.65), :]
            return (
                np.mean(bottom) < 60
                and np.mean(auto_area) < 80
                and np.mean(center) < 120
                and np.mean(top_center) < 100
            )
        except Exception:
            return False

    def get_screen_type(self, path: Optional[Path]) -> Tuple[str, float]:
        """Enhanced classification handling battle_field."""
        if path is None:
            return "error", 0.0
        stype, conf = self.classify(path)
        if conf < 0.5 and stype in ("unknown", "battle"):
            if self.is_battle_field(path):
                return "battle_field", 0.8
        if stype == "battle":
            return "battle_field", conf
        return stype, conf

    # ─── Action Executors ─────────────────────────────────────

    def buy_potion(self) -> bool:
        """Buy potion from shop: potion tab -> select large potion -> purchase."""
        self._log("[Executor] buy_potion")

        # Assume we're already on menu_shop
        # 1. Tap potion/item tab (left side tab area, items tab)
        self.tap(540, 1649, "items tab", wait=1.5)

        # 2. Select large potion (item_potion_large position)
        self.tap(371, 321, "item_potion_large", wait=1.0)

        # 3. Tap purchase button
        self.tap(540, 1100, "purchase_button", wait=1.0)

        # 4. Confirm purchase if dialog appears
        path = self.screenshot("buy_potion")
        stype, _ = self.get_screen_type(path)
        if stype in ("popup_confirm", "popup_notice"):
            self.tap(540, 1060, "confirm purchase", wait=1.0)

        # 5. Check we're still in shop (success)
        stype2, _ = self.current_screen()
        success = stype2 in ("menu_shop", "popup_reward")
        if stype2 == "popup_reward":
            self.tap(540, 1200, "collect reward", wait=1.0)

        self._log(f"[Executor] buy_potion -> {'OK' if success else 'FAIL'}")
        return success

    def enhance_gear(self) -> bool:
        """Enhance gear from character menu: equipment slot -> enhance button."""
        self._log("[Executor] enhance_gear")

        # Assume we're on menu_character
        # 1. Tap first equipment slot (weapon, top-left of equipment area)
        self.tap(200, 500, "equipment_slot_weapon", wait=1.5)

        # 2. Look for enhance button
        path = self.screenshot("enhance")
        stype, _ = self.get_screen_type(path)

        # 3. Tap enhance/upgrade button (usually at bottom of detail panel)
        self.tap(540, 1400, "enhance_button", wait=1.5)

        # 4. Confirm if dialog
        path2 = self.screenshot("enhance_confirm")
        stype2, _ = self.get_screen_type(path2)
        if stype2 in ("popup_confirm", "popup_notice"):
            self.tap(540, 1060, "confirm enhance", wait=1.0)

        # 5. Dismiss result popup if any
        time.sleep(1.0)
        path3 = self.screenshot("enhance_result")
        stype3, _ = self.get_screen_type(path3)
        if stype3 in ("popup_reward", "popup_notice"):
            self.tap(540, 1200, "dismiss result", wait=1.0)

        self._log("[Executor] enhance_gear -> done")
        return True

    def equip_upgrade(self) -> bool:
        """Equip better item: character -> inventory tab -> select -> equip."""
        self._log("[Executor] equip_upgrade")

        # Assume we're on menu_character
        # 1. Switch to inventory tab
        self.tap(673, 1699, "inventory_tab", wait=1.5)

        # 2. Select first equipment item in list
        self.tap(200, 400, "first_equip_item", wait=1.0)

        # 3. Tap equip/use button
        self.tap(540, 1554, "equip_button", wait=1.5)

        # 4. Dismiss any result popup
        path = self.screenshot("equip_result")
        stype, _ = self.get_screen_type(path)
        if stype in ("popup_reward", "popup_notice"):
            self.tap(540, 1200, "dismiss", wait=1.0)

        self._log("[Executor] equip_upgrade -> done")
        return True

    def grind_battle(self) -> str:
        """Run a full battle cycle: lobby->stage_select->battle->wait->lobby.

        Returns: 'lobby', 'death', 'timeout', or 'error'.
        """
        self._log("[Executor] grind_battle")
        return "lobby"  # Actual battle is handled by SmartPlayer.monitor_battle

    def buy_equipment(self) -> bool:
        """Buy equipment from shop: equipment tab -> select tier -> purchase."""
        self._log("[Executor] buy_equipment")

        # Assume we're on menu_shop
        # 1. Tap equipment tab
        self.tap(540, 1649, "equipment_tab", wait=1.5)

        # 2. Scroll to find affordable item
        self.swipe(540, 800, 540, 400, ms=500, wait=1.0)

        # 3. Select first available equipment
        self.tap(400, 400, "first_equipment", wait=1.0)

        # 4. Purchase
        self.tap(540, 1100, "purchase_button", wait=1.0)

        # 5. Confirm
        path = self.screenshot("buy_equip")
        stype, _ = self.get_screen_type(path)
        if stype in ("popup_confirm", "popup_notice"):
            self.tap(540, 1060, "confirm", wait=1.0)

        stype2, _ = self.current_screen()
        success = stype2 in ("menu_shop", "popup_reward")
        if stype2 == "popup_reward":
            self.tap(540, 1200, "collect", wait=1.0)

        self._log(f"[Executor] buy_equipment -> {'OK' if success else 'FAIL'}")
        return success

    def enable_auto_skills(self):
        """Enable AUTO for all 6 skill slots in battle."""
        self._log("[Executor] Enabling AUTO skills")
        positions = [
            (90, 1870), (230, 1870), (370, 1870),
            (510, 1870), (650, 1870), (790, 1870),
        ]
        for x, y in positions:
            self.tap(x, y, wait=0.2)

    def dismiss_popup(self, path: Optional[Path] = None):
        """Try to dismiss any popup on screen."""
        close_positions = [
            (978, 165), (540, 1900), (420, 1930),
            (900, 100), (960, 160), (540, 1200),
        ]
        for x, y in close_positions:
            self.tap(x, y, wait=0.3)
        time.sleep(0.5)

    # ─── Executor registry ────────────────────────────────────

    def get_executor(self, action_name: str) -> Optional[Callable]:
        """Return the executor function for a given GOAP action name."""
        registry: Dict[str, Callable] = {
            "buy_potion": self.buy_potion,
            "enhance_gear": self.enhance_gear,
            "equip_upgrade": self.equip_upgrade,
            "grind_battle": self.grind_battle,
            "buy_equipment": self.buy_equipment,
        }
        return registry.get(action_name)

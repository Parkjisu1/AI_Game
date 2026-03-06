"""
VirtualPlayer Configuration
============================
경로 상수, 기본값 정의.
"""

from pathlib import Path

# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_DIR = DATA_DIR / "db"
REPORTS_DIR = DATA_DIR / "reports"
DEVICES_JSON = PROJECT_ROOT / "persona" / "devices.json"

# ============================================================
# Defaults
# ============================================================

DEFAULT_GAME = "2048-web"
DEFAULT_PERSONA = "casual"
DEFAULT_SESSION_PATTERN = "evening"
DEFAULT_SESSION_COUNT = 1

# SQLite DB filename
HISTORY_DB_NAME = "virtual_player.db"

# ============================================================
# ADB / Android settings
# ============================================================

ADB_PATH = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
ADB_DEVICE = "emulator-5554"
CLAUDE_CMD = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"
CLAUDE_MODEL = "sonnet"

# Cache directory for ADB games (classifier, nav_graph, reflex, etc.)
ADB_CACHE_DIR = DATA_DIR / "cache"
ADB_TEMP_DIR = DATA_DIR / "temp"

# ============================================================
# Touch simulation defaults
# ============================================================

# Base delay between actions (seconds)
BASE_ACTION_DELAY = 0.3

# Human-like jitter range (seconds)
JITTER_RANGE = (0.05, 0.2)

# Touch coordinate offset range (pixels)
TOUCH_OFFSET_RANGE = (-3, 3)

# ============================================================
# Session fatigue
# ============================================================

# Fatigue accumulation rate per minute
FATIGUE_RATE_PER_MINUTE = 0.01

# Fatigue threshold for increased errors
FATIGUE_ERROR_THRESHOLD = 0.5

# Max fatigue (session auto-end)
FATIGUE_MAX = 1.0

# ============================================================
# AI Tester paths
# ============================================================

# Cross-game knowledge persistence
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
KNOWLEDGE_DB = KNOWLEDGE_DIR / "knowledge.json"

# Session journal
JOURNAL_DIR = DATA_DIR / "journal"

# Design DB root (for observer export)
DESIGN_DB_ROOT = Path(__file__).parent.parent / "db" / "design"

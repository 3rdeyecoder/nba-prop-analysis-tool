"""App-wide settings. Change APP_NAME / APP_SUBTITLE to rebrand."""
from pathlib import Path

APP_NAME = "Playmaker Lab"
APP_SUBTITLE = "🏀 NBA • 🏈 NFL • ⚾ MLB Player Analytics"
APP_ICON = "🧪🏀🏈⚾"

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
META_DIR = DATA_DIR / "meta"

# Recent-game windows offered in every sport (None = all qualifying games)
WINDOW_OPTIONS = {"Last 5": 5, "Last 10": 10, "Last 15": 15, "Last 20": 20, "All games": None}

# Below this many games the UI shows a small-sample note. It never blocks results.
SMALL_SAMPLE = 10

OVER_COLOR = "#2fbf71"
UNDER_COLOR = "#e5484d"
PUSH_COLOR = "#6b8afd"
AVG_COLOR = "#f59e0b"
LINE_COLOR = "#8b8f98"

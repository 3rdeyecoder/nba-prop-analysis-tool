# fetch_data.py — kept for backward compatibility. Prefer: python -m refresh.nba
#   python fetch_data.py                  # current season (regular season + playoffs)
#   python fetch_data.py 2024-25 2025-26  # specific seasons
import sys

from refresh.nba import main

if __name__ == "__main__":
    args = sys.argv[1:]
    sys.exit(main(["--seasons", *args] if args else []))

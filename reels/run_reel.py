"""Entry point: python reels/run_reel.py [--dry-run] [--force]

--dry-run : build the Reel and print the caption, do not post (default when DRY_RUN env is true)
--force   : ignore the minimum gap between posts
"""
import os
import sys
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parent / ".env")
except Exception:
    pass

import engine  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    dry = args.dry_run or os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes")

    gap_hours = float(os.getenv("MIN_GAP_HOURS", "3"))
    posted = [h for h in engine.load_history() if h.get("status") == "posted"]
    if posted and not args.force and not dry:
        last = datetime.fromisoformat(posted[-1]["date"])
        if datetime.now(timezone.utc) - last < timedelta(hours=gap_hours):
            print(f"[Doodlore] Last Reel was at {last.isoformat()}; next one is not due yet.")
            return 0

    result = engine.make_one(dry_run=dry)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

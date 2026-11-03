import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
QUEUE_DIR = BASE_DIR / "queue"
EVERGREEN_QUEUE = QUEUE_DIR / "evergreen"
TIMELY_QUEUE = QUEUE_DIR / "timely"
SCHEDULED_DIR = BASE_DIR / "scheduled"
PUBLISHED_DIR = BASE_DIR / "published"
DB_PATH = DATA_DIR / "art_schedule.db"

# Ensure all primary runtime paths exist
for d in [DATA_DIR, QUEUE_DIR, EVERGREEN_QUEUE, TIMELY_QUEUE, SCHEDULED_DIR, PUBLISHED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Load environment configuration
load_dotenv(BASE_DIR / ".env")

FB_PAGE_ID = os.getenv("FB_PAGE_ID", "").strip()
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "").strip()
DRY_RUN = os.getenv("DRY_RUN", "True").lower() in ("true", "1", "yes")

# Scheduling & Volume Controls
DAILY_POST_LIMIT = int(os.getenv("DAILY_POST_LIMIT", "6"))
EVERGREEN_POSTS_PER_DAY = int(os.getenv("EVERGREEN_POSTS_PER_DAY", "3"))

# Preferred UTC hours for posts
EVERGREEN_HOURS_UTC = [int(h.strip()) for h in os.getenv("EVERGREEN_HOURS_UTC", "9,17,22").split(",") if h.strip()]
TIMELY_HOURS_UTC = [int(h.strip()) for h in os.getenv("TIMELY_HOURS_UTC", "13,20").split(",") if h.strip()]

# Watch loop interval in minutes
WATCH_INTERVAL_MINUTES = int(os.getenv("WATCH_INTERVAL_MINUTES", "30"))

BRAND_NAME = os.getenv("BRAND_NAME", "The Inked Chronicle").strip()

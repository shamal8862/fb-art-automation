# The Inked Chronicle — Facebook Art Scheduling Engine

A dedicated backend automation system that bridges **Codex Desktop** (master-artisan ballpoint/pencil art generation) with **Meta Graph API** for scheduled social publishing.

---

## 🎯 Architecture

```
[ Codex Desktop ]
       │
       ▼ (Generates hyper-realistic art packages)
[ c:\xampp\htdocs\fb-art-automation\queue\ ]
       ├── evergreen/   <-- 30-40 buffer posts (scheduled 15-20 days ahead)
       └── timely/      <-- Day-relevant / breaking news / tributes (prioritized today)
       │
       ▼
[ scheduler.py / Windows Startup Background Check ]
       │
       ├─ Assigns optimal future calendar slots
       ├─ Calls Meta Graph API (published=false, scheduled_publish_time=timestamp)
       ├─ Records schedule history in SQLite (data/art_schedule.db)
       └─ Moves packages to scheduled/
```

---

## 📁 Package Format for Codex

Codex can drop posts as individual folders into either `queue/evergreen/` or `queue/timely/`:

```text
queue/
  evergreen/
    01_the_hands_that_held_us/
      ├── image.jpg (or .png)
      ├── caption.txt
      └── metadata.json (optional)
```

### 1. `caption.txt` (Required)
The emotional hook, question for engagement, and hashtags.

### 2. `metadata.json` (Optional)
```json
{
  "title": "The Hands That Held Us",
  "category": "universal_emotion",
  "type": "evergreen"
}
```

---

## 🚀 Usage & Commands

### 1. Check Active Schedule
View all upcoming scheduled posts across future dates:
```bash
python scheduler.py --status
```

### 2. Run Queue Processing Manually
```bash
python scheduler.py
```

### 3. Install Silent Windows Startup Runner
Double-click:
`startup/install_startup.bat`
This copies the silent VBS runner to your Windows Startup folder. Whenever you boot or log in to your laptop, it silently scans `queue/`, schedules any new packages into Facebook, and records them in `data/scheduler_startup.log`.

---

## 🔑 Going Live (Switching from DRY_RUN)

1. Open `.env`:
   ```ini
   FB_PAGE_ID=your_facebook_page_id
   FB_PAGE_ACCESS_TOKEN=your_page_access_token
   DRY_RUN=False
   ```
2. Run `python scheduler.py`. All scheduled posts will immediately populate in **Meta Business Suite Planner**!

"""
scheduler.py - Main Art Publishing & Scheduling Engine
Orchestrates incoming Codex art packages, assigns smart calendar slots, and schedules directly to Meta.
"""
import sys
import argparse
from datetime import datetime, timezone
from services.folder_watcher import FolderWatcher
from services.calendar_planner import CalendarPlanner
from services.meta_client import MetaSchedulerClient
from services.db_manager import record_scheduled_post, list_active_schedule
from config import BRAND_NAME, DRY_RUN, FB_PAGE_ID

def print_banner():
    mode = "DRY RUN (Simulation)" if DRY_RUN else "LIVE PUBLISHING (Meta Graph API)"
    print("=" * 65)
    print(f" {BRAND_NAME} — Facebook Art Scheduling Engine")
    print(f" Mode: {mode} | Target Page ID: {FB_PAGE_ID or 'Not Set'}")
    print("=" * 65)

def run_scheduler_cycle():
    print_banner()
    print("[1/4] Scanning queue folders for incoming artwork packages...")
    packages = FolderWatcher.scan_queue()

    if not packages:
        print("[Status] No new artwork packages waiting in queue.")
        show_active_schedule()
        return

    print(f"[2/4] Found {len(packages)} new package(s) to process:")
    for i, p in enumerate(packages, 1):
        print(f"      {i}. [{p.category.upper()}] {p.title} ({p.post_dir})")

    meta_client = MetaSchedulerClient()
    successful_count = 0

    print("\n[3/4] Assigning future slots and scheduling into Facebook...")
    for pkg in packages:
        try:
            # 1. Determine optimal calendar slot
            slot_timestamp = CalendarPlanner.get_next_slot(pkg.category)
            slot_iso = datetime.fromtimestamp(slot_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

            print(f"\n---> Processing: '{pkg.title}'")
            print(f"     Target Slot: {slot_iso} ({pkg.category})")

            # 2. Schedule with Meta Graph API
            meta_res = meta_client.schedule_photo_post(
                image_path=pkg.image_path,
                caption=pkg.caption,
                scheduled_timestamp=slot_timestamp
            )

            meta_fbid = meta_res.get("id") or "simulated_id"

            # 3. Record in SQLite
            record_scheduled_post(
                post_dir=pkg.post_dir,
                category=pkg.category,
                title=pkg.title,
                image_path=str(pkg.image_path),
                caption=pkg.caption,
                scheduled_timestamp=slot_timestamp,
                meta_fbid=meta_fbid,
                status="scheduled"
            )

            # 4. Move package to scheduled/
            FolderWatcher.archive_package(pkg)
            successful_count += 1
            print(f"     [OK] Scheduled and moved to scheduled/{pkg.category}/{pkg.post_dir}")

        except Exception as e:
            print(f"     [ERROR] Failed to schedule '{pkg.title}': {e}")
            record_scheduled_post(
                post_dir=pkg.post_dir,
                category=pkg.category,
                title=pkg.title,
                image_path=str(pkg.image_path),
                caption=pkg.caption,
                scheduled_timestamp=0,
                meta_fbid="",
                status="failed",
                error_message=str(e)
            )

    print(f"\n[4/4] Scheduling Cycle Complete: {successful_count}/{len(packages)} posts successfully queued.")
    show_active_schedule()

def show_active_schedule():
    active = list_active_schedule()
    print("\n" + "-" * 65)
    print(f" ACTIVE FUTURE SCHEDULE CALENDAR ({len(active)} posts currently queued)")
    print("-" * 65)
    if not active:
        print(" (No upcoming posts currently scheduled in local calendar)")
        return

    now_ts = int(datetime.now(timezone.utc).timestamp())
    for item in active:
        diff_hours = (item["scheduled_timestamp"] - now_ts) / 3600
        print(f" • [{item['category'].upper():<9}] {item['scheduled_iso']} (in {diff_hours:.1f}h) | {item['title'][:32]}")
    print("-" * 65)

def main():
    parser = argparse.ArgumentParser(description="Facebook Art Scheduler")
    parser.add_argument("--status", action="store_true", help="Display current active schedule")
    args = parser.parse_args()

    if args.status:
        print_banner()
        show_active_schedule()
    else:
        run_scheduler_cycle()

if __name__ == "__main__":
    main()

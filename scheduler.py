"""
scheduler.py - Resilient Art Publishing & Scheduling Engine
Features two-phase atomic publishing, crash reconciliation, simulation isolation, and background watch mode.
"""
import sys
import time
import argparse
import atexit
from datetime import datetime, timezone
from pathlib import Path

from config import BRAND_NAME, DRY_RUN, FB_PAGE_ID, WATCH_INTERVAL_MINUTES, DATA_DIR
from services.folder_watcher import FolderWatcher
from services.calendar_planner import CalendarPlanner
from services.meta_client import MetaSchedulerClient
from services.db_manager import (
    record_pending_post,
    confirm_post_scheduled,
    mark_post_failed,
    get_pending_posts,
    list_active_schedule
)

LOCK_FILE = DATA_DIR / "scheduler.lock"

def acquire_lock() -> bool:
    """Acquires a single-instance lock to prevent overlapping runs."""
    if LOCK_FILE.exists():
        try:
            mtime = LOCK_FILE.stat().st_mtime
            if time.time() - mtime > 900:  # Stale lock older than 15 minutes
                LOCK_FILE.unlink(missing_ok=True)
            else:
                return False
        except Exception:
            return False

    try:
        LOCK_FILE.write_text(str(datetime.now(timezone.utc)), encoding="utf-8")
        atexit.register(release_lock)
        return True
    except Exception:
        return False

def release_lock():
    LOCK_FILE.unlink(missing_ok=True)

def print_banner():
    mode = "DRY RUN (Simulation — Queue Untouched)" if DRY_RUN else "LIVE PUBLISHING (Meta Graph API)"
    print("=" * 68)
    print(f" {BRAND_NAME} — Facebook Art Scheduling Engine")
    print(f" Mode: {mode} | Target Page ID: {FB_PAGE_ID or 'Not Set'}")
    print("=" * 68)

def reconcile_pending_posts(meta_client: MetaSchedulerClient):
    """Reconciles interrupted uploads by checking Meta's live scheduled queue."""
    pending = get_pending_posts(include_simulated=DRY_RUN)
    if not pending:
        return

    print(f"[Reconciliation] Found {len(pending)} unconfirmed post(s) from prior runs. Verifying...")
    live_posts = meta_client.get_live_scheduled_posts()
    live_captions = {p.get("message", "").strip(): p.get("id") for p in live_posts if "message" in p}

    for p in pending:
        post_dir = p["post_dir"]
        caption = p["caption"].strip()
        matched_id = live_captions.get(caption)

        if matched_id:
            print(f"  -> Reconciled: '{p['title']}' was confirmed on Facebook (FBID: {matched_id})")
            confirm_post_scheduled(post_dir, matched_id, p["image_path"])
        else:
            print(f"  -> Resetting unconfirmed pending post: '{p['title']}' for clean retry")
            mark_post_failed(post_dir, "Interrupted before Facebook confirmation")

def run_scheduler_cycle():
    if not acquire_lock():
        print("[Status] Another scheduler instance is currently running. Skipping cycle.")
        return

    try:
        print_banner()
        meta_client = MetaSchedulerClient()

        # Step 1: Reconcile any prior pending posts
        reconcile_pending_posts(meta_client)

        # Step 2: Scan queue
        print("[1/4] Scanning queue folders for verified artwork packages...")
        packages = FolderWatcher.scan_queue(is_simulation=DRY_RUN)

        if not packages:
            print("[Status] No new artwork packages waiting in queue.")
            show_active_schedule()
            return

        print(f"[2/4] Found {len(packages)} new package(s) to process:")
        for i, p in enumerate(packages, 1):
            print(f"      {i}. [{p.category.upper()}] {p.title} ({p.post_dir})")

        successful_count = 0
        print("\n[3/4] Assigning collision-free slots & scheduling into Facebook...")

        for pkg in packages:
            try:
                # 1. Determine optimal slot
                slot_timestamp = CalendarPlanner.get_next_slot(pkg.category)
                slot_iso = datetime.fromtimestamp(slot_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

                print(f"\n---> Processing: '{pkg.title}'")
                print(f"     Target Slot: {slot_iso} ({pkg.category})")

                # Phase 1: Record pending row before calling Meta
                record_pending_post(
                    post_dir=pkg.post_dir,
                    category=pkg.category,
                    title=pkg.title,
                    image_path=str(pkg.image_path),
                    caption=pkg.caption,
                    scheduled_timestamp=slot_timestamp,
                    is_simulation=DRY_RUN
                )

                # Phase 2: Transmit to Facebook
                meta_res = meta_client.schedule_photo_post(
                    image_path=pkg.image_path,
                    caption=pkg.caption,
                    scheduled_timestamp=slot_timestamp
                )

                meta_fbid = meta_res.get("id") or "simulated_id"

                # Archive package (only moves in LIVE mode, stays in queue in DRY RUN)
                final_image_path = FolderWatcher.archive_package(pkg, is_simulation=DRY_RUN)

                # Confirm in database
                confirm_post_scheduled(pkg.post_dir, meta_fbid, str(final_image_path))
                successful_count += 1
                print(f"     [OK] Confirmed with Meta FBID: {meta_fbid}")

            except Exception as e:
                print(f"     [ERROR] Failed to schedule '{pkg.title}': {e}")
                mark_post_failed(pkg.post_dir, str(e))

        print(f"\n[4/4] Scheduling Cycle Complete: {successful_count}/{len(packages)} posts successfully processed.")
        show_active_schedule()

    finally:
        release_lock()

def show_active_schedule():
    active = list_active_schedule()
    print("\n" + "-" * 68)
    print(f" ACTIVE FUTURE SCHEDULE CALENDAR ({len(active)} posts currently queued)")
    print("-" * 68)
    if not active:
        print(" (No upcoming posts currently scheduled in local calendar)")
        return

    now_ts = int(datetime.now(timezone.utc).timestamp())
    for item in active:
        diff_hours = (item["scheduled_timestamp"] - now_ts) / 3600
        sim_tag = " [SIM]" if item.get("is_simulation") else ""
        print(f" • [{item['category'].upper():<9}] {item['scheduled_iso']} (in {diff_hours:.1f}h){sim_tag} | {item['title'][:32]}")
    print("-" * 68)

def watch_loop():
    print(f"Starting Facebook Art Scheduler in WATCH mode (interval: {WATCH_INTERVAL_MINUTES}m)...")
    try:
        while True:
            run_scheduler_cycle()
            print(f"\nSleeping for {WATCH_INTERVAL_MINUTES} minutes until next scan. (Ctrl+C to stop)...")
            time.sleep(WATCH_INTERVAL_MINUTES * 60)
    except KeyboardInterrupt:
        print("\nWatch loop stopped by user.")

def main():
    parser = argparse.ArgumentParser(description="Facebook Art Scheduler")
    parser.add_argument("--status", action="store_true", help="Display current active schedule")
    parser.add_argument("--watch", action="store_true", help="Run recurring scan loop in background")
    args = parser.parse_args()

    if args.status:
        print_banner()
        show_active_schedule()
    elif args.watch:
        watch_loop()
    else:
        run_scheduler_cycle()

if __name__ == "__main__":
    main()

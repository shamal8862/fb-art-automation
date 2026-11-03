"""
tests/test_scheduler.py - Comprehensive Standard Library Unit & Regression Test Suite
Verifies collision avoidance, simulation isolation, fail-fast credentials, and integrity checks.
"""
import os
import shutil
import unittest
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from PIL import Image

import config
from services.db_manager import (
    init_db,
    record_pending_post,
    confirm_post_scheduled,
    is_post_processed,
    is_timestamp_occupied,
    get_scheduled_posts_for_date
)
from services.calendar_planner import CalendarPlanner
from services.meta_client import MetaSchedulerClient
from services.folder_watcher import FolderWatcher

class TestSchedulerSuite(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.tmp_path = Path(self.test_dir)
        self.test_db = self.tmp_path / "test_art.db"
        self.test_queue = self.tmp_path / "queue"
        self.test_evergreen = self.test_queue / "evergreen"
        self.test_timely = self.test_queue / "timely"
        self.test_scheduled = self.tmp_path / "scheduled"

        for d in [self.test_evergreen, self.test_timely, self.test_scheduled]:
            d.mkdir(parents=True, exist_ok=True)

        self.orig_db = config.DB_PATH
        self.orig_queue = config.QUEUE_DIR
        self.orig_evergreen = config.EVERGREEN_QUEUE
        self.orig_timely = config.TIMELY_QUEUE
        self.orig_scheduled = config.SCHEDULED_DIR

        config.DB_PATH = self.test_db
        config.QUEUE_DIR = self.test_queue
        config.EVERGREEN_QUEUE = self.test_evergreen
        config.TIMELY_QUEUE = self.test_timely
        config.SCHEDULED_DIR = self.test_scheduled

        import services.db_manager as dbm
        import services.folder_watcher as fwm
        self.orig_dbm_db = dbm.DB_PATH
        dbm.DB_PATH = self.test_db
        fwm.EVERGREEN_QUEUE = self.test_evergreen
        fwm.TIMELY_QUEUE = self.test_timely
        fwm.SCHEDULED_DIR = self.test_scheduled

        dbm.init_db()

    def tearDown(self):
        config.DB_PATH = self.orig_db
        config.QUEUE_DIR = self.orig_queue
        config.EVERGREEN_QUEUE = self.orig_evergreen
        config.TIMELY_QUEUE = self.orig_timely
        config.SCHEDULED_DIR = self.orig_scheduled

        import services.db_manager as dbm
        import services.folder_watcher as fwm
        dbm.DB_PATH = self.orig_dbm_db
        fwm.EVERGREEN_QUEUE = self.orig_evergreen
        fwm.TIMELY_QUEUE = self.orig_timely
        fwm.SCHEDULED_DIR = self.orig_scheduled

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_package(self, folder_path: Path, title: str, has_ready_flag: bool = True, is_corrupt: bool = False):
        folder_path.mkdir(parents=True, exist_ok=True)
        img_file = folder_path / "image.jpg"

        if is_corrupt:
            img_file.write_bytes(b"corrupt non-image binary data")
        else:
            im = Image.new("RGB", (200, 200), color="blue")
            im.save(img_file)

        (folder_path / "caption.txt").write_text(f"Emotional caption for {title} #art", encoding="utf-8")
        if has_ready_flag:
            (folder_path / "ready.flag").write_text("ready", encoding="utf-8")

    def test_missing_credentials_fails_fast_in_live_mode(self):
        """Verify that live mode (DRY_RUN=False) raises ValueError when credentials are missing."""
        with self.assertRaises(ValueError):
            MetaSchedulerClient(page_id="", access_token="", dry_run=False)

    def test_dry_run_simulation_isolation(self):
        """Verify that dry-run mode does not move packages from queue and does not block live mode."""
        evergreen_dir = config.EVERGREEN_QUEUE / "mock_post"
        self._create_mock_package(evergreen_dir, "Mock Post")

        # 1. Scan in simulation mode
        pkgs = FolderWatcher.scan_queue(is_simulation=True)
        self.assertEqual(len(pkgs), 1)

        # 2. Archive in simulation mode
        ret_path = FolderWatcher.archive_package(pkgs[0], is_simulation=True)
        self.assertTrue(evergreen_dir.exists(), "Package must remain in queue during dry run")
        self.assertEqual(ret_path, pkgs[0].image_path)

        # 3. Record simulated post
        record_pending_post("mock_post", "evergreen", "Mock", str(ret_path), "caption", 1800000000, is_simulation=True)

        # 4. In live mode, this package should NOT be marked as processed
        self.assertFalse(is_post_processed("mock_post", include_simulated=False), "Simulated run must not block live scheduling")

    def test_timely_slots_never_collide(self):
        """Verify that multiple timely posts on the same day never get identical timestamps."""
        base_ts = CalendarPlanner.get_next_slot(category="timely")

        # Reserve the base slot in database
        record_pending_post("timely_1", "timely", "Post 1", "path", "cap", base_ts, is_simulation=False)
        confirm_post_scheduled("timely_1", "fb_123", "path")

        # Second timely post must get a different slot spaced away
        second_ts = CalendarPlanner.get_next_slot(category="timely")
        self.assertNotEqual(second_ts, base_ts, "Timely slots must not collide")
        self.assertGreaterEqual(abs(second_ts - base_ts), 1500, f"Slots should be at least 25 minutes apart")

    def test_evergreen_posts_per_day_strictly_enforced(self):
        """Verify that EVERGREEN_POSTS_PER_DAY is strictly respected."""
        orig_limit = config.EVERGREEN_POSTS_PER_DAY
        config.EVERGREEN_POSTS_PER_DAY = 2
        try:
            slot1 = CalendarPlanner.get_next_slot(category="evergreen")
            record_pending_post("ev_1", "evergreen", "EV 1", "path", "cap", slot1, is_simulation=False)
            confirm_post_scheduled("ev_1", "fb_1", "path")

            slot2 = CalendarPlanner.get_next_slot(category="evergreen")
            record_pending_post("ev_2", "evergreen", "EV 2", "path", "cap", slot2, is_simulation=False)
            confirm_post_scheduled("ev_2", "fb_2", "path")

            dt1 = datetime.fromtimestamp(slot1, tz=timezone.utc)
            dt2 = datetime.fromtimestamp(slot2, tz=timezone.utc)
            self.assertEqual(dt1.date(), dt2.date(), "First two evergreen posts should be on the same date")

            # Third evergreen post must roll to next day because limit is 2
            slot3 = CalendarPlanner.get_next_slot(category="evergreen")
            dt3 = datetime.fromtimestamp(slot3, tz=timezone.utc)
            self.assertGreater(dt3.date(), dt1.date(), "Third evergreen post must roll to the next day when limit is 2")
        finally:
            config.EVERGREEN_POSTS_PER_DAY = orig_limit

    def test_corrupt_images_are_skipped(self):
        """Verify that corrupted image packages are safely skipped by the watcher."""
        pkg_dir = config.EVERGREEN_QUEUE / "corrupt_pkg"
        self._create_mock_package(pkg_dir, "Corrupt", is_corrupt=True)

        pkgs = FolderWatcher.scan_queue(is_simulation=True)
        self.assertEqual(len(pkgs), 0, "Corrupt packages must not be ingested")

if __name__ == "__main__":
    unittest.main()

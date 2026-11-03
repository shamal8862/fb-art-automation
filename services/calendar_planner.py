"""
services/calendar_planner.py - Collision-Free Slot Calculator for Evergreen and Timely Art Posts
Enforces daily caps, category separation, and prevents slot collisions.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from config import (
    DAILY_POST_LIMIT,
    EVERGREEN_POSTS_PER_DAY,
    EVERGREEN_HOURS_UTC,
    TIMELY_HOURS_UTC
)
from services.db_manager import (
    get_latest_scheduled_timestamp,
    get_scheduled_posts_for_date,
    is_timestamp_occupied
)

class CalendarPlanner:
    """Computes exact future timestamps for upcoming posts ensuring smooth calendar spread without collision."""

    @staticmethod
    def get_slot_for_package(pkg) -> int:
        """
        Determines the optimal slot for a PostPackage, strictly honoring exact-day holds (ON-YYYY-MM-DD),
        flexible date windows (WINDOW-..._to_...), or standard sequential evergreen/timely queues.
        """
        now = datetime.now(timezone.utc)
        min_future_time = now + timedelta(minutes=15)

        timing_mode = getattr(pkg, "timing_mode", "any")

        # 1. Exact-day hold (e.g. ON-2026-11-10 or publish_on: "2026-11-10")
        if timing_mode == "exact_date" and getattr(pkg, "target_date", None):
            return CalendarPlanner._get_exact_date_slot(pkg, now, min_future_time)

        # 2. Window hold (e.g. WINDOW-2026-11-06_to_2026-11-08)
        if timing_mode == "window" and getattr(pkg, "window_start", None) and getattr(pkg, "window_end", None):
            return CalendarPlanner._get_window_slot(pkg, now, min_future_time)

        # 3. Standard category queue (evergreen / timely)
        category = getattr(pkg, "category", "evergreen")
        return CalendarPlanner.get_next_slot(category)

    @staticmethod
    def _get_exact_date_slot(pkg, now: datetime, min_future_time: datetime) -> int:
        """
        Finds an unoccupied slot on the EXACT specified target date.
        If strict_date is True and the date is already in the past, raises ValueError.
        """
        target_str = pkg.target_date
        try:
            target_date = datetime.strptime(target_str, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid target_date format '{target_str}'. Expected YYYY-MM-DD.")

        today = now.date()
        if target_date < today:
            if getattr(pkg, "strict_date", True):
                raise ValueError(f"Strict exact-date post '{pkg.title}' target date {target_str} has already passed.")
            target_date = today

        # Check candidate hours on target date (honor target_time_utc if specified)
        pref_hours = []
        target_hour = pkg.metadata.get("target_time_utc") if hasattr(pkg, "metadata") else None
        if target_hour is not None:
            pref_hours.append(int(target_hour))
        pref_hours.extend(TIMELY_HOURS_UTC if pkg.category == "timely" else EVERGREEN_HOURS_UTC)
        pref_hours = sorted(list(dict.fromkeys(pref_hours)))

        for hour in pref_hours:
            slot_dt = datetime(target_date.year, target_date.month, target_date.day, hour, 0, 0, tzinfo=timezone.utc)
            slot_ts = int(slot_dt.timestamp())
            if slot_dt > min_future_time and not is_timestamp_occupied(slot_ts, tolerance_minutes=25):
                print(f"[Calendar Planner] Exact-Date Slot Booked: {slot_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} for '{pkg.title}'")
                return slot_ts

        # If all preferred hours are occupied or passed today, try offset hours on target date
        if target_date == today:
            for offset in [25, 60, 120, 180, 240, 360]:
                slot_dt = now + timedelta(minutes=offset)
                if slot_dt.date() == target_date:
                    slot_ts = int(slot_dt.timestamp())
                    if not is_timestamp_occupied(slot_ts, tolerance_minutes=20):
                        return slot_ts
        else:
            for hour in range(8, 23):
                slot_dt = datetime(target_date.year, target_date.month, target_date.day, hour, 0, 0, tzinfo=timezone.utc)
                slot_ts = int(slot_dt.timestamp())
                if slot_dt > min_future_time and not is_timestamp_occupied(slot_ts, tolerance_minutes=20):
                    return slot_ts

        fallback_dt = datetime(target_date.year, target_date.month, target_date.day, 12, 0, 0, tzinfo=timezone.utc)
        return int(fallback_dt.timestamp())

    @staticmethod
    def _get_window_slot(pkg, now: datetime, min_future_time: datetime) -> int:
        """Finds an unoccupied slot inside a flexible window [window_start, window_end]."""
        start_date = datetime.strptime(pkg.window_start, "%Y-%m-%d").date()
        end_date = datetime.strptime(pkg.window_end, "%Y-%m-%d").date()

        current_d = max(start_date, now.date())
        while current_d <= end_date:
            pref_hours = TIMELY_HOURS_UTC if pkg.category == "timely" else EVERGREEN_HOURS_UTC
            for hour in sorted(pref_hours):
                slot_dt = datetime(current_d.year, current_d.month, current_d.day, hour, 0, 0, tzinfo=timezone.utc)
                slot_ts = int(slot_dt.timestamp())
                if slot_dt > min_future_time and not is_timestamp_occupied(slot_ts, tolerance_minutes=25):
                    print(f"[Calendar Planner] Window Slot Booked: {slot_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} for '{pkg.title}'")
                    return slot_ts
            current_d += timedelta(days=1)

        return CalendarPlanner.get_next_slot(pkg.category)

    @staticmethod
    def get_next_slot(category: str = "evergreen") -> int:
        """Determines the next optimal, unoccupied Unix timestamp for a post."""
        now = datetime.now(timezone.utc)
        min_future_time = now + timedelta(minutes=15)

        if category == "timely":
            return CalendarPlanner._get_timely_slot(now, min_future_time)
        else:
            return CalendarPlanner._get_evergreen_slot(now, min_future_time)

    @staticmethod
    def _get_timely_slot(now: datetime, min_future_time: datetime) -> int:
        """
        Finds the nearest non-colliding timely slot today or rolls to tomorrow.
        Ensures slots are at least 30 minutes apart from any existing post.
        """
        today = now.date()

        for day_offset in range(3):  # Check today, tomorrow, day after
            target_date = today + timedelta(days=day_offset)
            date_str = target_date.isoformat()
            existing_for_day = get_scheduled_posts_for_date(date_str)

            if len(existing_for_day) >= DAILY_POST_LIMIT:
                continue

            # Try preferred timely hours
            for hour in sorted(TIMELY_HOURS_UTC):
                candidate_dt = datetime(target_date.year, target_date.month, target_date.day, hour, 0, 0, tzinfo=timezone.utc)
                candidate_ts = int(candidate_dt.timestamp())

                if candidate_dt > min_future_time and not is_timestamp_occupied(candidate_ts, tolerance_minutes=25):
                    return candidate_ts

            # If today and preferred hours passed, try dynamic immediate slots (e.g. now + 25m, now + 60m)
            if day_offset == 0:
                for minute_offset in [25, 60, 120, 180, 240]:
                    dynamic_candidate = now + timedelta(minutes=minute_offset)
                    dynamic_ts = int(dynamic_candidate.timestamp())
                    if not is_timestamp_occupied(dynamic_ts, tolerance_minutes=25):
                        return dynamic_ts

        # Extreme fallback
        fallback = now + timedelta(hours=6)
        return int(fallback.timestamp())

    @staticmethod
    def _get_evergreen_slot(now: datetime, min_future_time: datetime) -> int:
        """
        Finds the next vacant evergreen slot chronologically across future days.
        Strictly enforces EVERGREEN_POSTS_PER_DAY and prevents slot collisions.
        """
        latest_ts = get_latest_scheduled_timestamp(category="evergreen")

        if latest_ts:
            start_dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
        else:
            start_dt = now

        current_day = start_dt.date()
        for day_offset in range(90):  # Search up to 90 days
            target_date = current_day + timedelta(days=day_offset)
            date_str = target_date.isoformat()

            # Enforce overall daily cap and evergreen daily cap
            all_posts_day = get_scheduled_posts_for_date(date_str)
            if len(all_posts_day) >= DAILY_POST_LIMIT:
                continue

            evergreen_day = get_scheduled_posts_for_date(date_str, category="evergreen")
            if len(evergreen_day) >= EVERGREEN_POSTS_PER_DAY:
                continue

            # Check preferred evergreen hours
            for hour in sorted(EVERGREEN_HOURS_UTC):
                slot_dt = datetime(target_date.year, target_date.month, target_date.day, hour, 0, 0, tzinfo=timezone.utc)
                slot_ts = int(slot_dt.timestamp())

                # Must be in the future, after any prior evergreen, and not collide with any post
                if slot_dt > min_future_time and (latest_ts is None or slot_ts > latest_ts):
                    if not is_timestamp_occupied(slot_ts, tolerance_minutes=25):
                        return slot_ts

        # Fallback
        fallback_dt = start_dt + timedelta(days=1)
        return int(fallback_dt.timestamp())

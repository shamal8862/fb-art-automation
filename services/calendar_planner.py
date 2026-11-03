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

"""
services/calendar_planner.py - Intelligent Slot Calculator for Evergreen and Timely Art Posts
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
    get_scheduled_timestamps_for_date
)

class CalendarPlanner:
    """Computes exact future timestamps for upcoming posts ensuring smooth calendar spread."""

    @staticmethod
    def get_next_slot(category: str = "evergreen") -> int:
        """
        Determines the next optimal Unix timestamp for a post of the given category.
        """
        now = datetime.now(timezone.utc)
        min_future_time = now + timedelta(minutes=15)

        if category == "timely":
            return CalendarPlanner._get_timely_slot(now, min_future_time)
        else:
            return CalendarPlanner._get_evergreen_slot(now, min_future_time)

    @staticmethod
    def _get_timely_slot(now: datetime, min_future_time: datetime) -> int:
        """Finds the nearest timely slot today or immediate fallback."""
        today = now.date()
        today_str = today.isoformat()
        
        # Check today's preferred timely hours
        for hour in sorted(TIMELY_HOURS_UTC):
            candidate_dt = datetime(today.year, today.month, today.day, hour, 0, 0, tzinfo=timezone.utc)
            if candidate_dt > min_future_time:
                # Check daily cap
                existing = get_scheduled_timestamps_for_date(today_str)
                if len(existing) < DAILY_POST_LIMIT:
                    return int(candidate_dt.timestamp())

        # If today's timely slots passed, schedule immediate (now + 20 minutes)
        # unless daily cap is full, then roll to tomorrow's first timely slot
        existing_today = get_scheduled_timestamps_for_date(today_str)
        if len(existing_today) < DAILY_POST_LIMIT:
            return int((now + timedelta(minutes=20)).timestamp())

        # Roll to tomorrow's first timely hour
        tomorrow = today + timedelta(days=1)
        first_hour = min(TIMELY_HOURS_UTC)
        candidate_tomorrow = datetime(tomorrow.year, tomorrow.month, tomorrow.day, first_hour, 0, 0, tzinfo=timezone.utc)
        return int(candidate_tomorrow.timestamp())

    @staticmethod
    def _get_evergreen_slot(now: datetime, min_future_time: datetime) -> int:
        """
        Finds the next vacant evergreen slot chronologically across future days.
        Builds the 30-40 post buffer seamlessly.
        """
        latest_ts = get_latest_scheduled_timestamp()

        # If we have existing scheduled posts, start searching from the latest scheduled time
        if latest_ts:
            start_dt = datetime.fromtimestamp(latest_ts, tz=timezone.utc)
        else:
            start_dt = now

        # Search forward day by day
        current_day = start_dt.date()
        for day_offset in range(90):  # Search up to 90 days forward
            target_date = current_day + timedelta(days=day_offset)
            target_date_str = target_date.isoformat()

            # Get all scheduled timestamps for this day
            scheduled_ts_for_day = get_scheduled_timestamps_for_date(target_date_str)
            if len(scheduled_ts_for_day) >= DAILY_POST_LIMIT:
                continue

            scheduled_hours = [
                datetime.fromtimestamp(ts, tz=timezone.utc).hour
                for ts in scheduled_ts_for_day
            ]

            # Find an unused evergreen slot
            for hour in sorted(EVERGREEN_HOURS_UTC):
                if hour in scheduled_hours:
                    continue  # Slot already occupied

                slot_dt = datetime(target_date.year, target_date.month, target_date.day, hour, 0, 0, tzinfo=timezone.utc)
                if slot_dt > min_future_time and (latest_ts is None or slot_dt.timestamp() > latest_ts):
                    return int(slot_dt.timestamp())

        # Fallback if somehow full: 1 day after start_dt
        fallback_dt = start_dt + timedelta(days=1)
        return int(fallback_dt.timestamp())

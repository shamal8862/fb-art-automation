"""
services/meta_client.py - Facebook Graph API Client for Post Scheduling
"""
import time
import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
from config import FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN, DRY_RUN

logger = logging.getLogger("MetaClient")

class MetaSchedulerClient:
    """Handles communication with Facebook Graph API to schedule photo posts."""
    
    GRAPH_API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, page_id: Optional[str] = None, access_token: Optional[str] = None, dry_run: Optional[bool] = None):
        self.page_id = page_id or FB_PAGE_ID
        self.access_token = access_token or FB_PAGE_ACCESS_TOKEN
        self.dry_run = DRY_RUN if dry_run is None else dry_run

    def schedule_photo_post(
        self,
        image_path: Path,
        caption: str,
        scheduled_timestamp: int
    ) -> Dict[str, Any]:
        """
        Schedules a photo post to a Facebook Page.
        Uses POST /{page-id}/photos with published=false and scheduled_publish_time.
        """
        now_ts = int(datetime.now(timezone.utc).timestamp())
        min_lead_time = now_ts + 600  # Meta minimum is 10 minutes (600s)
        max_horizon = now_ts + (75 * 86400)  # Meta maximum is 75 days

        if scheduled_timestamp < min_lead_time:
            raise ValueError(f"Scheduled time ({scheduled_timestamp}) must be at least 10 minutes in the future (current + 600s: {min_lead_time})")
        if scheduled_timestamp > max_horizon:
            raise ValueError(f"Scheduled time exceeds Meta's 75-day maximum scheduling window.")

        sched_iso = datetime.fromtimestamp(scheduled_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        if self.dry_run or not self.page_id or not self.access_token:
            simulated_fbid = f"dry_run_{int(time.time() * 1000)}"
            print(f"[Meta Client - DRY RUN] Successfully simulated schedule for {image_path.name}")
            print(f"                       Scheduled Date: {sched_iso}")
            print(f"                       Simulated FBID: {simulated_fbid}")
            return {
                "id": simulated_fbid,
                "post_id": f"{self.page_id or '0000000000'}_{simulated_fbid}",
                "dry_run": True
            }

        url = f"{self.BASE_URL}/{self.page_id}/photos"
        payload = {
            "access_token": self.access_token,
            "message": caption,
            "published": "false",
            "scheduled_publish_time": str(scheduled_timestamp)
        }

        print(f"[Meta Client] Scheduling '{image_path.name}' to Facebook at {sched_iso}...")

        with open(image_path, "rb") as img_file:
            files = {"source": (image_path.name, img_file, "image/jpeg")}
            response = requests.post(url, data=payload, files=files, timeout=45)

        if response.status_code == 200:
            result = response.json()
            print(f"[Meta Client] SUCCESS! Post scheduled with Meta Photo ID: {result.get('id')}")
            return result
        else:
            err_data = response.json() if "application/json" in response.headers.get("content-type", "") else response.text
            raise RuntimeError(f"Facebook Graph API Error (HTTP {response.status_code}): {err_data}")

    def get_live_scheduled_posts(self) -> List[Dict[str, Any]]:
        """Queries Facebook for the page's currently scheduled posts."""
        if self.dry_run or not self.page_id or not self.access_token:
            return []

        url = f"{self.BASE_URL}/{self.page_id}/scheduled_posts"
        params = {"access_token": self.access_token, "limit": 100}
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json().get("data", [])
        return []

"""
services/meta_client.py - Facebook Graph API Client for Post Scheduling
Fails loudly if live credentials are missing, and supports post reconciliation.
"""
import time
import requests
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pathlib import Path
from config import FB_PAGE_ID, FB_PAGE_ACCESS_TOKEN, IG_USER_ID, DRY_RUN

logger = logging.getLogger("MetaClient")

class MetaSchedulerClient:
    """Handles communication with Facebook & Instagram Graph API to schedule and publish posts."""
    
    GRAPH_API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

    def __init__(self, page_id: Optional[str] = None, access_token: Optional[str] = None, ig_user_id: Optional[str] = None, dry_run: Optional[bool] = None):
        self.dry_run = DRY_RUN if dry_run is None else dry_run
        self.page_id = (page_id or FB_PAGE_ID).strip()
        self.access_token = (access_token or FB_PAGE_ACCESS_TOKEN).strip()
        self.ig_user_id = (ig_user_id or IG_USER_ID).strip()

        # CRITICAL FAIL-FAST CHECK: Never silently simulate in live mode!
        if not self.dry_run:
            if not self.page_id or not self.access_token:
                raise ValueError(
                    "FATAL: Missing Facebook credentials for LIVE mode (DRY_RUN=False). "
                    "Please set FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN in .env or switch DRY_RUN=True."
                )

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
        min_lead_time = now_ts + 600  # Meta minimum: 10 minutes
        max_horizon = now_ts + (75 * 86400)  # Meta maximum: 75 days

        if scheduled_timestamp < min_lead_time:
            raise ValueError(f"Scheduled time ({scheduled_timestamp}) must be at least 10 minutes in future (current + 600s: {min_lead_time})")
        if scheduled_timestamp > max_horizon:
            raise ValueError(f"Scheduled time exceeds Meta's 75-day maximum window.")

        sched_iso = datetime.fromtimestamp(scheduled_timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Explicit simulation branch
        if self.dry_run:
            simulated_fbid = f"sim_{int(time.time() * 1000)}"
            print(f"[Meta Client - SIMULATION] Would schedule '{image_path.name}' to Facebook at {sched_iso}")
            return {
                "id": simulated_fbid,
                "post_id": f"{self.page_id or '0000000000'}_{simulated_fbid}",
                "dry_run": True
            }

        # Live execution branch (Two-step feed scheduling for Meta Business Suite Planner visibility)
        print(f"[Meta Client] Step 1/2: Uploading unpublished photo media...")
        photo_url = f"{self.BASE_URL}/{self.page_id}/photos"
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        
        with open(image_path, "rb") as img_file:
            files = {"source": (image_path.name, img_file, mime_type)}
            photo_resp = requests.post(
                photo_url,
                data={"access_token": self.access_token, "published": "false"},
                files=files,
                timeout=60
            )

        if photo_resp.status_code != 200:
            try:
                err_data = photo_resp.json()
            except Exception:
                err_data = photo_resp.text
            raise RuntimeError(f"Facebook Photo Upload Error (HTTP {photo_resp.status_code}): {err_data}")

        media_fbid = photo_resp.json().get("id")
        
        # Retrieve public CDN image URL from uploaded Facebook media for Instagram reuse
        cdn_image_url = None
        try:
            cdn_resp = requests.get(
                f"{self.BASE_URL}/{media_fbid}",
                params={"access_token": self.access_token, "fields": "source"},
                timeout=15
            )
            if cdn_resp.status_code == 200:
                cdn_image_url = cdn_resp.json().get("source")
        except Exception as e:
            logger.warning(f"Could not retrieve Facebook CDN URL for photo {media_fbid}: {e}")

        print(f"[Meta Client] Step 2/2: Scheduling feed post to Meta Business Suite Planner (Slot: {sched_iso})...")

        import json
        feed_url = f"{self.BASE_URL}/{self.page_id}/feed"
        feed_payload = {
            "access_token": self.access_token,
            "message": caption,
            "published": "false",
            "scheduled_publish_time": str(scheduled_timestamp),
            "attached_media": json.dumps([{"media_fbid": media_fbid}])
        }

        feed_resp = requests.post(feed_url, data=feed_payload, timeout=30)
        if feed_resp.status_code == 200:
            result = feed_resp.json()
            result["media_fbid"] = media_fbid
            result["cdn_image_url"] = cdn_image_url
            print(f"[Meta Client] SUCCESS! Scheduled Feed Post ID: {result.get('id')}")
            return result
        else:
            try:
                err_data = feed_resp.json()
            except Exception:
                err_data = feed_resp.text
            raise RuntimeError(f"Facebook Feed Schedule Error (HTTP {feed_resp.status_code}): {err_data}")

    def publish_to_instagram(self, image_url: str, caption: str) -> Dict[str, Any]:
        """
        Publishes a photo post to the connected Instagram Business account (@doodlore_arts).
        Uses Meta's two-step container creation & media_publish sequence.
        """
        if self.dry_run:
            simulated_ig_id = f"sim_ig_{int(time.time() * 1000)}"
            print(f"[Meta Client - SIMULATION] Would publish to Instagram @doodlore_arts")
            return {"id": simulated_ig_id, "dry_run": True}

        if not self.ig_user_id or not self.access_token:
            raise ValueError("FATAL: Missing IG_USER_ID or FB_PAGE_ACCESS_TOKEN for Instagram publishing.")

        # Step 1: Create Instagram media container
        print(f"[Meta Client - Instagram] Step 1/2: Creating media container...")
        container_url = f"{self.BASE_URL}/{self.ig_user_id}/media"
        c_resp = requests.post(
            container_url,
            data={
                "access_token": self.access_token,
                "image_url": image_url,
                "caption": caption
            },
            timeout=30
        )
        if c_resp.status_code != 200:
            raise RuntimeError(f"Instagram Container Creation Error (HTTP {c_resp.status_code}): {c_resp.text}")

        container_id = c_resp.json().get("id")
        print(f"[Meta Client - Instagram] Media container created: {container_id}. Processing...")
        time.sleep(2)

        # Step 2: Publish container live
        print(f"[Meta Client - Instagram] Step 2/2: Publishing container to feed...")
        pub_url = f"{self.BASE_URL}/{self.ig_user_id}/media_publish"
        p_resp = requests.post(
            pub_url,
            data={
                "access_token": self.access_token,
                "creation_id": container_id
            },
            timeout=30
        )
        if p_resp.status_code != 200:
            raise RuntimeError(f"Instagram Media Publish Error (HTTP {p_resp.status_code}): {p_resp.text}")

        ig_result = p_resp.json()
        print(f"[Meta Client - Instagram] SUCCESS! Live Instagram Post ID: {ig_result.get('id')}")
        return ig_result

    def publish_facebook_story(self, image_path: Path) -> Dict[str, Any]:
        """
        Publishes an image as an active 24-hour Story to the Facebook Page.
        Uses POST /{page-id}/photo_stories with an unpublished photo.
        """
        if self.dry_run:
            print(f"[Meta Client - SIMULATION] Would publish Facebook Page Story: {image_path.name}")
            return {"success": True, "dry_run": True}

        photo_url = f"{self.BASE_URL}/{self.page_id}/photos"
        mime_type = "image/png" if image_path.suffix.lower() == ".png" else "image/jpeg"
        with open(image_path, "rb") as img_file:
            files = {"source": (image_path.name, img_file, mime_type)}
            r_up = requests.post(
                photo_url,
                data={"access_token": self.access_token, "published": "false"},
                files=files,
                timeout=60
            )

        if r_up.status_code != 200:
            logger.warning(f"Failed to upload photo for Facebook Story: {r_up.text}")
            return {"error": r_up.text}

        photo_id = r_up.json().get("id")
        story_url = f"{self.BASE_URL}/{self.page_id}/photo_stories"
        r_story = requests.post(
            story_url,
            data={"access_token": self.access_token, "photo_id": photo_id},
            timeout=30
        )
        if r_story.status_code == 200:
            res = r_story.json()
            print(f"[Meta Client - Facebook Story] SUCCESS! Story published: {res.get('post_id')}")
            return res
        else:
            logger.warning(f"Facebook Story publish failed: {r_story.text}")
            return {"error": r_story.text}

    def publish_instagram_story(self, image_url: str) -> Dict[str, Any]:
        """
        Publishes an image as an active 24-hour Story to the connected Instagram account.
        Uses POST /{ig-user-id}/media with media_type=STORIES.
        """
        if self.dry_run:
            print(f"[Meta Client - SIMULATION] Would publish Instagram Story")
            return {"id": "sim_ig_story", "dry_run": True}

        if not self.ig_user_id or not self.access_token:
            return {"error": "Missing IG_USER_ID or access token"}

        container_url = f"{self.BASE_URL}/{self.ig_user_id}/media"
        c_resp = requests.post(
            container_url,
            data={"access_token": self.access_token, "image_url": image_url, "media_type": "STORIES"},
            timeout=30
        )
        if c_resp.status_code != 200:
            logger.warning(f"Instagram Story container error: {c_resp.text}")
            return {"error": c_resp.text}

        container_id = c_resp.json().get("id")
        time.sleep(2)

        pub_url = f"{self.BASE_URL}/{self.ig_user_id}/media_publish"
        p_resp = requests.post(
            pub_url,
            data={"access_token": self.access_token, "creation_id": container_id},
            timeout=30
        )
        if p_resp.status_code == 200:
            res = p_resp.json()
            print(f"[Meta Client - Instagram Story] SUCCESS! Story published: {res.get('id')}")
            return res
        else:
            logger.warning(f"Instagram Story publish error: {p_resp.text}")
            return {"error": p_resp.text}

    def schedule_dual_post(
        self,
        image_path: Path,
        caption: str,
        scheduled_timestamp: int,
        publish_ig_now: bool = False
    ) -> Dict[str, Any]:
        """
        Schedules to Facebook Page Planner, and either publishes to Instagram immediately
        or returns the CDN URL and container info for delayed publishing.
        """
        fb_result = self.schedule_photo_post(image_path, caption, scheduled_timestamp)
        cdn_url = fb_result.get("cdn_image_url")
        ig_result = None

        if publish_ig_now and cdn_url:
            ig_result = self.publish_to_instagram(cdn_url, caption)

        return {
            "fb_post_id": fb_result.get("id"),
            "fb_media_fbid": fb_result.get("media_fbid"),
            "cdn_image_url": cdn_url,
            "ig_post_id": ig_result.get("id") if ig_result else None,
            "scheduled_timestamp": scheduled_timestamp
        }

    def get_live_scheduled_posts(self) -> List[Dict[str, Any]]:
        """Queries Facebook for the page's currently scheduled posts to support reconciliation."""
        if self.dry_run or not self.page_id or not self.access_token:
            return []

        url = f"{self.BASE_URL}/{self.page_id}/scheduled_posts"
        params = {"access_token": self.access_token, "limit": 100}
        try:
            resp = requests.get(url, params=params, timeout=20)
            if resp.status_code == 200:
                return resp.json().get("data", [])
            print(f"[Meta Client] Warning: Failed to fetch scheduled posts: HTTP {resp.status_code}")
            return []
        except Exception as e:
            print(f"[Meta Client] Warning: Could not connect to Facebook scheduled_posts: {e}")
            return []

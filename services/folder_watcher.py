"""
services/folder_watcher.py - Ingests artwork packages, validates file integrity, and archives safely
"""
import os
import json
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image
from config import EVERGREEN_QUEUE, TIMELY_QUEUE, SCHEDULED_DIR, DRY_RUN
from services.db_manager import is_post_processed

class PostPackage:
    def __init__(
        self,
        post_dir: str,
        category: str,
        package_path: Path,
        image_paths: List[Path],
        caption: str,
        title: str,
        metadata: Dict[str, Any]
    ):
        self.post_dir = post_dir
        self.category = category
        self.package_path = package_path
        self.image_paths = image_paths if isinstance(image_paths, list) else [image_paths]
        self.image_path = self.image_paths[0]
        self.is_carousel = len(self.image_paths) > 1
        self.caption = caption
        self.title = title
        self.metadata = metadata
        self.timing_mode = metadata.get("timing_mode", "any")
        self.target_date = metadata.get("target_date")
        self.window_start = metadata.get("window_start")
        self.window_end = metadata.get("window_end")
        self.strict_date = metadata.get("strict_date", True)
        self.content_pillar = metadata.get("content_pillar")

class FolderWatcher:
    """Monitors queue/evergreen and queue/timely with integrity verification."""

    SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

    @classmethod
    def scan_queue(cls, is_simulation: bool = DRY_RUN) -> List[PostPackage]:
        """Scans queue directories and returns verified, unposted packages."""
        packages = []
        packages.extend(cls._scan_category_dir(EVERGREEN_QUEUE, "evergreen", is_simulation))
        packages.extend(cls._scan_category_dir(TIMELY_QUEUE, "timely", is_simulation))
        return packages

    @classmethod
    def _scan_category_dir(cls, category_dir: Path, category: str, is_simulation: bool) -> List[PostPackage]:
        found = []
        if not category_dir.exists():
            return found

        for entry in sorted(category_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                pkg = cls._parse_directory_package(entry, category, is_simulation)
                if pkg:
                    found.append(pkg)
        return found

    @classmethod
    def _parse_directory_package(cls, dir_path: Path, category: str, is_simulation: bool) -> Optional[PostPackage]:
        post_dir = dir_path.name

        # Skip if already scheduled/published (simulation check obeys is_simulation flag)
        if is_post_processed(post_dir, include_simulated=is_simulation):
            return None

        # Check for optional ready.flag or .ready file
        ready_flag = (dir_path / "ready.flag").exists() or (dir_path / ".ready").exists()

        # Find all valid image files in alphanumeric order (e.g. 01.png, 02.png or image1.png, image2.png)
        image_files = sorted([
            file for file in dir_path.iterdir()
            if file.suffix.lower() in cls.SUPPORTED_EXTS and not file.name.startswith(".")
        ], key=lambda x: x.name.lower())

        if not image_files or image_files[0].stat().st_size < 500:
            return None  # Missing or empty file

        # If no explicit ready flag, verify files aren't actively being written (age > 2 seconds)
        if not ready_flag:
            for img_f in image_files:
                file_age = time.time() - img_f.stat().st_mtime
                if file_age < 2.0:
                    print(f"[Watcher] Skipping '{post_dir}': file actively being written (age={file_age:.1f}s)")
                    return None

        # Verify image integrity via PIL
        try:
            for img_f in image_files:
                with Image.open(img_f) as img:
                    img.verify()
        except Exception as e:
            print(f"[Watcher] Image corruption detected in '{post_dir}': {e}")
            return None

        # Find caption file
        caption_file = dir_path / "caption.txt"
        if not caption_file.exists():
            txt_files = list(dir_path.glob("*.txt"))
            caption_file = txt_files[0] if txt_files else None

        if not caption_file:
            return None

        try:
            caption = caption_file.read_text(encoding="utf-8").strip()
        except Exception:
            caption = caption_file.read_text(encoding="latin-1").strip()

        if not caption:
            return None

        # Parse metadata
        metadata = {}
        meta_file = dir_path / "metadata.json"
        if meta_file.exists():
            try:
                metadata = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Parse timing rules from folder name prefix
        import re
        folder_name = dir_path.name
        timing_mode = "any"
        target_date = None
        window_start = None
        window_end = None
        strict_date = True

        on_match = re.match(r"^ON-(\d{4}-\d{2}-\d{2})(?:__(.+))?$", folder_name, re.IGNORECASE)
        win_match = re.match(r"^WINDOW-(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})(?:__(.+))?$", folder_name, re.IGNORECASE)

        if on_match:
            timing_mode = "exact_date"
            target_date = on_match.group(1)
            strict_date = True
        elif win_match:
            timing_mode = "window"
            window_start = win_match.group(1)
            window_end = win_match.group(2)
            strict_date = False

        # Metadata can enrich or override
        if "publish_on" in metadata:
            timing_mode = "exact_date"
            target_date = metadata["publish_on"]
        if "publish_not_before" in metadata and "publish_not_after" in metadata:
            timing_mode = "window"
            window_start = metadata["publish_not_before"]
            window_end = metadata["publish_not_after"]
        if "strict_date" in metadata:
            strict_date = bool(metadata["strict_date"])

        metadata["timing_mode"] = timing_mode
        metadata["target_date"] = target_date
        metadata["window_start"] = window_start
        metadata["window_end"] = window_end
        metadata["strict_date"] = strict_date

        if metadata.get("title"):
            title = metadata["title"]
        else:
            cleaned_name = re.sub(r"^(ON-[0-9-]+|WINDOW-[0-9-_to]+|ANY)__", "", dir_path.name, flags=re.IGNORECASE)
            title = cleaned_name.replace("_", " ").replace("-", " ").title()

        return PostPackage(
            post_dir=post_dir,
            category=metadata.get("type", category),
            package_path=dir_path,
            image_paths=image_files,
            caption=caption,
            title=title,
            metadata=metadata
        )

    @classmethod
    def archive_package(cls, pkg: PostPackage, is_simulation: bool = DRY_RUN) -> Path:
        """
        Moves scheduled package to scheduled/ in live mode.
        In simulation mode, leaves the package safely in queue/ and returns original image path.
        """
        if is_simulation:
            print(f"[Watcher - SIMULATION] Package '{pkg.post_dir}' preserved in queue for future live runs.")
            return pkg.image_path

        target_category_dir = SCHEDULED_DIR / pkg.category
        target_category_dir.mkdir(parents=True, exist_ok=True)
        dest_dir = target_category_dir / pkg.package_path.name

        if dest_dir.exists():
            shutil.rmtree(dest_dir)

        shutil.move(str(pkg.package_path), str(dest_dir))
        final_image_path = dest_dir / pkg.image_path.name
        print(f"[Watcher] Successfully moved '{pkg.post_dir}' to {dest_dir}")
        return final_image_path

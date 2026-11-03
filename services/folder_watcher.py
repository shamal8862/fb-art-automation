"""
services/folder_watcher.py - Scans queue folders, validates post packages, and archives scheduled items
"""
import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from config import EVERGREEN_QUEUE, TIMELY_QUEUE, SCHEDULED_DIR
from services.db_manager import is_post_processed

class PostPackage:
    def __init__(
        self,
        post_dir: str,
        category: str,
        package_path: Path,
        image_path: Path,
        caption: str,
        title: str,
        metadata: Dict[str, Any]
    ):
        self.post_dir = post_dir
        self.category = category
        self.package_path = package_path
        self.image_path = image_path
        self.caption = caption
        self.title = title
        self.metadata = metadata

class FolderWatcher:
    """Monitors queue/evergreen and queue/timely for newly prepared artwork packages."""

    SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

    @classmethod
    def scan_queue(cls) -> List[PostPackage]:
        """Scans both evergreen and timely directories and returns valid unposted packages."""
        packages = []
        packages.extend(cls._scan_category_dir(EVERGREEN_QUEUE, "evergreen"))
        packages.extend(cls._scan_category_dir(TIMELY_QUEUE, "timely"))
        return packages

    @classmethod
    def _scan_category_dir(cls, category_dir: Path, category: str) -> List[PostPackage]:
        found = []
        if not category_dir.exists():
            return found

        for entry in sorted(category_dir.iterdir()):
            if entry.is_dir():
                pkg = cls._parse_directory_package(entry, category)
                if pkg:
                    found.append(pkg)
        return found

    @classmethod
    def _parse_directory_package(cls, dir_path: Path, category: str) -> Optional[PostPackage]:
        post_dir = dir_path.name

        # Skip if already recorded as scheduled
        if is_post_processed(post_dir):
            return None

        # Find image file
        image_file = None
        for file in dir_path.iterdir():
            if file.suffix.lower() in cls.SUPPORTED_EXTS and not file.name.startswith("."):
                image_file = file
                break

        if not image_file or image_file.stat().st_size < 1000:
            return None  # No valid image or corrupt/empty file

        # Find caption file
        caption_file = dir_path / "caption.txt"
        if not caption_file.exists():
            # Try any .txt file
            txt_files = list(dir_path.glob("*.txt"))
            caption_file = txt_files[0] if txt_files else None

        if not caption_file:
            return None  # Caption required

        try:
            caption = caption_file.read_text(encoding="utf-8").strip()
        except Exception:
            caption = caption_file.read_text(encoding="latin-1").strip()

        if not caption:
            return None

        # Parse optional metadata
        metadata = {}
        meta_file = dir_path / "metadata.json"
        if meta_file.exists():
            try:
                metadata = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Determine title
        title = metadata.get("title") or dir_path.name.replace("_", " ").replace("-", " ").title()

        return PostPackage(
            post_dir=post_dir,
            category=metadata.get("type", category),
            package_path=dir_path,
            image_path=image_file,
            caption=caption,
            title=title,
            metadata=metadata
        )

    @classmethod
    def archive_package(cls, pkg: PostPackage):
        """Moves a scheduled package from queue/ to scheduled/."""
        target_category_dir = SCHEDULED_DIR / pkg.category
        target_category_dir.mkdir(parents=True, exist_ok=True)
        dest = target_category_dir / pkg.package_path.name

        if dest.exists():
            shutil.rmtree(dest)

        shutil.move(str(pkg.package_path), str(dest))
        print(f"[Watcher] Moved '{pkg.post_dir}' to {dest}")

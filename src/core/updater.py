"""
GitHub Releases Updater Client.
Checks for new releases, parses semantic versioning, detects platform-matching assets,
and handles streaming downloads.
"""

from __future__ import annotations

import contextlib
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.version import parse as parse_version

from src.core.version import GITHUB_REPO, __version__


@dataclass
class ReleaseInfo:
    tag_name: str
    version_str: str
    name: str
    release_notes: str
    html_url: str
    published_at: str
    download_url: str | None = None
    asset_name: str | None = None
    asset_size_bytes: int | None = None

    @property
    def is_newer_than_current(self) -> bool:
        try:
            current_v = parse_version(__version__.lstrip("v"))
            remote_v = parse_version(self.version_str.lstrip("v"))
            return remote_v > current_v
        except Exception:
            return False


class GitHubUpdater:
    """Manages update checking and downloading via GitHub Releases API."""

    def __init__(self, repo: str | None = None):
        self.repo = repo or GITHUB_REPO
        self.api_url = f"https://api.github.com/repos/{self.repo}/releases/latest"

    def check_for_updates(self, timeout_sec: float = 5.0) -> ReleaseInfo | None:
        """
        Query GitHub API for the latest release.
        Returns ReleaseInfo if a valid release is found, None if no releases or on network failure.
        """
        req = urllib.request.Request(
            self.api_url,
            headers={
                "User-Agent": f"Grabber-Updater/{__version__}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                if response.status != 200:
                    return None
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, Exception):
            # Graceful failure on offline mode, 404 repo/releases, or timeout
            return None

        tag_name = data.get("tag_name", "")
        version_str = tag_name.lstrip("v")
        name = data.get("name") or tag_name
        body = data.get("body", "Nessuna nota di rilascio fornita.")
        html_url = data.get("html_url", f"https://github.com/{self.repo}/releases")
        published_at = data.get("published_at", "")

        # Find matching asset for the current OS
        asset_info = self._find_platform_asset(data.get("assets", []))

        return ReleaseInfo(
            tag_name=tag_name,
            version_str=version_str,
            name=name,
            release_notes=body,
            html_url=html_url,
            published_at=published_at,
            download_url=asset_info.get("download_url"),
            asset_name=asset_info.get("name"),
            asset_size_bytes=asset_info.get("size"),
        )

    def _find_platform_asset(self, assets: list[dict[str, Any]]) -> dict[str, Any]:
        """Match release assets against the current operating system."""
        platform = sys.platform
        keywords = []
        if platform == "win32":
            keywords = ["windows", "win", ".exe"]
        elif platform == "darwin":
            keywords = ["macos", "mac", "darwin"]
        else:
            keywords = ["linux", "ubuntu"]

        # First pass: check for keyword in asset name
        for asset in assets:
            aname = asset.get("name", "").lower()
            if any(kw in aname for kw in keywords):
                return {
                    "download_url": asset.get("browser_download_url"),
                    "name": asset.get("name"),
                    "size": asset.get("size"),
                }

        # Fallback: if single zip or tar asset is available
        if assets:
            return {
                "download_url": assets[0].get("browser_download_url"),
                "name": assets[0].get("name"),
                "size": assets[0].get("size"),
            }

        return {}

    def download_asset(
        self,
        download_url: str,
        destination_path: str,
        progress_callback: Callable[[float, int, int], None] | None = None,
        chunk_size: int = 65536,
    ) -> str:
        """Download release asset with progress updates."""
        req = urllib.request.Request(
            download_url,
            headers={"User-Agent": f"Grabber-Updater/{__version__}"},
        )

        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp_dest = dest.with_suffix(dest.suffix + ".tmp")

        try:
            with urllib.request.urlopen(req) as resp:
                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                with open(tmp_dest, "wb") as f:
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            frac = downloaded / total_size if total_size > 0 else 0.0
                            progress_callback(min(1.0, frac), downloaded, total_size)

            tmp_dest.replace(dest)
        except Exception:
            if tmp_dest.exists():
                with contextlib.suppress(OSError):
                    tmp_dest.unlink()
            raise

        return str(dest)

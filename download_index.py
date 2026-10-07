"""Persistent index of successfully downloaded source links."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from media_types import DownloadedMedia

LOGGER = logging.getLogger(__name__)


class DownloadIndex:
    """Store successful downloads in ``downloads/index.json`` atomically."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write({"version": 1, "downloads": {}})
            LOGGER.info("Created download index path=%s", self.path)

    def contains(self, source_url: str) -> bool:
        with self._lock:
            return source_url in self._read()["downloads"]

    def record(
        self, source_url: str, platform: str, media: list[DownloadedMedia]
    ) -> None:
        """Record only after every returned media file has been saved."""
        with self._lock:
            payload = self._read()
            payload["downloads"][source_url] = {
                "platform": platform,
                "downloaded_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "files": [item.path.name for item in media],
            }
            self._write(payload)
        LOGGER.info(
            "Recorded successful download platform=%s files=%s",
            platform,
            [item.path.name for item in media],
        )

    def _read(self) -> dict[str, object]:
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Could not read download index; starting with an empty index: %s", exc)
            return {"version": 1, "downloads": {}}
        if not isinstance(payload, dict) or not isinstance(payload.get("downloads"), dict):
            LOGGER.warning("Download index has an invalid structure; starting with an empty index")
            return {"version": 1, "downloads": {}}
        return payload

    def _write(self, payload: dict[str, object]) -> None:
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        temporary.replace(self.path)

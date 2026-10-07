"""TikTok source plugin backed by SaveTik's public browser endpoint."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from media_types import DownloadedMedia, MediaKind, SourceError
from savetik_client import SaveTikClient, SaveTikError
from storage import available_path, stream_to_file

LOGGER = logging.getLogger(__name__)


class TikTokSource:
    name = "tiktok"
    hosts = {"tiktok.com", "tiktokv.com"}

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == item or host.endswith(f".{item}") for item in self.hosts)

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        try:
            LOGGER.info("Source download started source=%s", self.name)
            result = SaveTikClient().parse(url)
            title = result.title or (title_hint or "")
            target = available_path(destination, title, ".mp4")
            stream_to_file(result.video_url, target)
        except SaveTikError as exc:
            raise SourceError(str(exc)) from exc
        except OSError as exc:
            raise SourceError(f"本地保存失败：{exc}") from exc
        LOGGER.info("Source download completed source=%s target=%s", self.name, target.name)
        return [DownloadedMedia(MediaKind.VIDEO, target, title, url, "SaveTik")]

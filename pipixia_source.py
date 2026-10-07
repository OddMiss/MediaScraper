"""Pipixia source plugin backed by the HelloTik parse flow."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hellotik_client import HelloTikClient, HelloTikError
from media_types import DownloadedMedia, MediaKind, SourceError
from storage import available_path, stream_to_file

LOGGER = logging.getLogger(__name__)


class PipixiaSource:
    name = "pipixia"
    # Share links normally use h5.pipix.com.  Keep both parent domains so
    # future desktop and mobile share URLs are recognized as well.
    hosts = {"pipix.com", "pipixia.com"}

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == item or host.endswith(f".{item}") for item in self.hosts)

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        try:
            LOGGER.info("Source download started source=%s", self.name)
            data = HelloTikClient().parse(url)
            title = str(data.get("title") or "").strip() or (title_hint or "")
            video_url = self._first_video_url(data)
            target = available_path(destination, title, ".mp4")
            stream_to_file(video_url, target)
        except HelloTikError as exc:
            raise SourceError(str(exc)) from exc
        except OSError as exc:
            raise SourceError(f"本地保存失败：{exc}") from exc
        LOGGER.info("Source download completed source=%s target=%s", self.name, target.name)
        return [DownloadedMedia(MediaKind.VIDEO, target, title, url, "HelloTik")]

    @staticmethod
    def _first_video_url(data: dict[str, Any]) -> str:
        videos = data.get("videos") or []
        if not isinstance(videos, list) or not videos:
            raise SourceError("该皮皮虾作品没有可下载的视频。")
        item = videos[0]
        if isinstance(item, str):
            return item
        if isinstance(item, dict) and isinstance(item.get("url"), str):
            return item["url"]
        raise SourceError("解析结果中没有视频地址。")

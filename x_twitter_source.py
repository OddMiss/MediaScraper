"""X/Twitter source plugin backed by X-Twitter-Downloader."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import requests

from media_types import DownloadedMedia, MediaKind, SourceError
from storage import available_path, safe_stem, stream_to_file
from x_twitter_client import XTwitterClient, XTwitterError

LOGGER = logging.getLogger(__name__)


class XTwitterSource:
    name = "x_twitter"
    hosts = {"x.com", "twitter.com"}

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == domain or host.endswith(f".{domain}") for domain in self.hosts)

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        LOGGER.info("Source download started source=%s", self.name)
        try:
            result = XTwitterClient().parse(url)
            title = result.title or (title_hint or "")
            filename_title = title or safe_stem("")
            media: list[DownloadedMedia] = []
            for video in result.videos:
                video_title = (
                    filename_title
                    if len(result.videos) == 1
                    else f"{filename_title} - {video.index}"
                )
                target = available_path(destination, video_title, ".mp4")
                stream_to_file(video.url, target)
                media.append(
                    DownloadedMedia(
                        MediaKind.VIDEO, target, title, url, "X-Twitter-Downloader"
                    )
                )
                LOGGER.info(
                    "Source video saved source=%s video_index=%d quality=%s target=%s",
                    self.name,
                    video.index,
                    video.quality,
                    target.name,
                )
        except XTwitterError as exc:
            raise SourceError(str(exc)) from exc
        except requests.RequestException as exc:
            raise SourceError(f"X 视频下载失败：{exc}") from exc
        except OSError as exc:
            raise SourceError(f"本地保存失败：{exc}") from exc
        LOGGER.info("Source download completed source=%s files=%d", self.name, len(media))
        return media

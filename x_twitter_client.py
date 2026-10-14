"""Client for the public X-Twitter-Downloader browser parse endpoint."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

LOGGER = logging.getLogger(__name__)


class XTwitterError(RuntimeError):
    """The X downloader could not resolve a public post video."""


@dataclass(frozen=True)
class XVideo:
    index: int
    url: str
    quality: str


@dataclass(frozen=True)
class XTwitterResult:
    title: str
    videos: list[XVideo]


class XTwitterClient:
    BASE_URL = "https://x-twitter-downloader.com"
    PARSE_URL = f"{BASE_URL}/api/parse-video"

    def __init__(self, timeout: tuple[int, int] = (15, 90)) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
                ),
                "Origin": self.BASE_URL,
                "Referer": f"{self.BASE_URL}/",
            }
        )

    def parse(self, source_url: str) -> XTwitterResult:
        LOGGER.info("X-Twitter-Downloader parse requested")
        try:
            response = self.session.post(
                self.PARSE_URL, json={"url": source_url}, timeout=self.timeout
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise XTwitterError(f"X 视频解析服务请求失败：{exc}") from exc
        except ValueError as exc:
            raise XTwitterError("X 视频解析服务返回了非 JSON 响应。") from exc

        if not isinstance(payload, dict):
            raise XTwitterError("X 视频解析结果格式异常。")
        if payload.get("success") is not True:
            raise XTwitterError(str(payload.get("error") or "X 视频解析失败。"))

        videos = self._select_videos(payload.get("videos"))
        if not videos:
            raise XTwitterError("该 X 帖文没有可下载的 MP4 视频。")
        title = str(payload.get("title") or "").strip()
        if not title:
            title = str(payload.get("author") or "").strip()
        LOGGER.info(
            "X-Twitter-Downloader parse completed videos=%d title_present=%s",
            len(videos),
            bool(title),
        )
        return XTwitterResult(title=title, videos=videos)

    @staticmethod
    def _select_videos(options: Any) -> list[XVideo]:
        if not isinstance(options, list):
            return []
        best: dict[int, tuple[tuple[int, int, int], XVideo]] = {}
        for option in options:
            if not isinstance(option, dict):
                continue
            url = option.get("direct_download_url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                continue
            if str(option.get("format_ext") or "").lower() != "mp4":
                continue
            parsed = urlparse(url)
            if not parsed.hostname:
                continue
            try:
                index = int(option.get("video_index", 1))
                width = int(option.get("width") or 0)
                height = int(option.get("quality") or 0)
                bitrate = int(option.get("bitrate") or 0)
            except (TypeError, ValueError):
                continue
            quality = str(option.get("qualityDesc") or f"{width}x{height}")
            candidate = XVideo(index=index, url=url, quality=quality)
            score = (width * height, bitrate, width)
            if index not in best or score > best[index][0]:
                best[index] = (score, candidate)
        return [best[index][1] for index in sorted(best)]

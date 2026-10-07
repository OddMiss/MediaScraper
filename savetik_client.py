"""Minimal client for SaveTik's public TikTok search flow."""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass

import requests

LOGGER = logging.getLogger(__name__)


class SaveTikError(RuntimeError):
    """SaveTik could not return a usable TikTok download resource."""


@dataclass(frozen=True)
class SaveTikResult:
    title: str
    video_url: str


class SaveTikClient:
    BASE_URL = "https://savetik.io"
    PAGE_URL = f"{BASE_URL}/zh-cn"
    SEARCH_URL = f"{BASE_URL}/api/ajaxSearch"

    def __init__(self, timeout: tuple[int, int] = (15, 90)) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131 Safari/537.36"
                ),
                "Referer": self.PAGE_URL,
                "Origin": self.BASE_URL,
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def parse(self, source_url: str) -> SaveTikResult:
        source_url = source_url.strip()
        if not source_url.startswith(("https://", "http://")):
            raise SaveTikError("链接必须以 http:// 或 https:// 开头。")

        # Establishing the same first-party session as the browser makes this
        # request behave consistently when SaveTik changes its cookie policy.
        LOGGER.info("SaveTik parse requested")
        self.session.get(self.PAGE_URL, timeout=self.timeout)
        response = self.session.post(
            self.SEARCH_URL,
            data={"q": source_url, "cursor": "0", "page": "0", "lang": "zh-cn"},
            timeout=self.timeout,
        )
        try:
            result = response.json()
        except ValueError as exc:
            raise SaveTikError("SaveTik 返回了非 JSON 响应。") from exc
        if not response.ok or not isinstance(result, dict):
            raise SaveTikError(f"SaveTik 服务返回 HTTP {response.status_code}。")
        if result.get("status") != "ok":
            raise SaveTikError(str(result.get("msg") or "SaveTik 未能解析该 TikTok 链接。"))

        fragment = result.get("data")
        if not isinstance(fragment, str):
            raise SaveTikError("SaveTik 解析结果格式异常。")
        title = self._title(fragment)
        video_url = self._best_mp4_url(fragment)
        LOGGER.info("SaveTik parse completed title_present=%s", bool(title))
        return SaveTikResult(title=title, video_url=video_url)

    @staticmethod
    def _title(fragment: str) -> str:
        match = re.search(r"<h3[^>]*>(.*?)</h3>", fragment, re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return html.unescape(re.sub(r"<[^>]+>", "", match.group(1))).strip()

    @staticmethod
    def _best_mp4_url(fragment: str) -> str:
        candidates: list[tuple[str, str]] = []
        for match in re.finditer(
            r"<a\b(?P<attrs>[^>]*)>(?P<label>.*?)</a>",
            fragment,
            re.IGNORECASE | re.DOTALL,
        ):
            attrs = match.group("attrs")
            href = re.search(r'''\bhref=["']([^"']+)["']''', attrs, re.IGNORECASE)
            if not href:
                continue
            label = html.unescape(re.sub(r"<[^>]+>", "", match.group("label"))).strip()
            if "MP4" in label.upper():
                candidates.append((label.upper(), html.unescape(href.group(1))))
        if not candidates:
            raise SaveTikError("SaveTik 未返回可下载的 MP4 视频。")
        # SaveTik puts its normal MP4 first. It is the page's default download
        # choice and is substantially more reliable than the optional HD file,
        # which can be several times larger and expire sooner.
        return candidates[0][1]

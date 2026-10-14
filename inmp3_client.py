"""Read IN音乐网 search results and their public MP3 playback URLs."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

import requests

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://inmp3.com"
_CODE = re.compile(r"\blet\s+code\s*=\s*['\"]([A-Za-z0-9+/=]+)['\"]")
_BLOCKED_VERSION = re.compile(r"(?:翻唱|伴奏|现场|live|cover|remix|dj版|演唱会)", re.I)


class InMp3Error(RuntimeError):
    """The site did not provide a usable, verified MP3 result."""


@dataclass(frozen=True)
class SearchResult:
    rid: int
    title: str
    artist: str
    album: str


@dataclass(frozen=True)
class ExactTrack:
    rid: int
    audio_url: str


class _ResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[SearchResult] = []
        self._depth = 0
        self._rid: int | None = None
        self._field: str | None = None
        self._field_depth = 0
        self._values: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "div":
            return
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if not self._depth:
            if "result-item" not in classes:
                return
            rid = attributes.get("data-rid") or ""
            self._rid = int(rid) if rid.isdigit() else None
            self._values = {"title": "", "artist": "", "album": ""}
            self._depth = 1
            return
        self._depth += 1
        for field in self._values:
            if f"result-{field}" in classes:
                self._field = field
                self._field_depth = self._depth
                break

    def handle_data(self, data: str) -> None:
        if self._depth and self._field:
            self._values[self._field] += data

    def handle_endtag(self, tag: str) -> None:
        if tag != "div" or not self._depth:
            return
        if self._field and self._depth == self._field_depth:
            self._field = None
        self._depth -= 1
        if not self._depth and self._rid is not None:
            self.results.append(
                SearchResult(
                    self._rid,
                    self._values["title"].strip(),
                    self._values["artist"].strip(),
                    self._values["album"].removeprefix("专辑:").strip(),
                )
            )


def _same(left: str, right: str) -> bool:
    # Ignore only insignificant whitespace; do not strip versions, featured artists,
    # punctuation or parenthesized suffixes from either title.
    return re.sub(r"\s+", " ", left).strip().casefold() == re.sub(r"\s+", " ", right).strip().casefold()


class InMp3Client:
    def __init__(self, timeout: tuple[int, int] = (15, 30)) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": BASE_URL + "/"})

    def find_exact(self, artist: str, title: str) -> ExactTrack | None:
        query = f"{artist} {title}"
        url = f"{BASE_URL}/so/{quote(query, safe='')}/"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        parser = _ResultParser()
        parser.feed(response.text)
        candidates = [
            item for item in parser.results
            if _same(item.title, title)
            and _same(item.artist, artist)
            and not _BLOCKED_VERSION.search(item.album)
        ]
        LOGGER.info(
            "IN音乐网 search artist=%s title=%s results=%d exact=%d",
            artist, title, len(parser.results), len(candidates),
        )
        if not candidates:
            return None
        # Site order is significant: only the first exact result is eligible.
        result = candidates[0]
        response = self.session.get(f"{BASE_URL}/song/{result.rid}/", timeout=self.timeout)
        response.raise_for_status()
        self._verify_detail(response.text, artist, title)
        code = _CODE.search(response.text)
        if not code:
            raise InMp3Error("精确匹配歌曲的页面没有 MP3 播放地址。")
        try:
            audio_url = base64.b64decode(code.group(1), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise InMp3Error("MP3 播放地址格式无效。") from exc
        parsed = urlparse(audio_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not (hostname == "kuwo.cn" or hostname.endswith(".kuwo.cn")) or not parsed.path.lower().endswith(".mp3"):
            raise InMp3Error("MP3 播放地址不在允许的音频域名内。")
        LOGGER.info("IN音乐网 exact track selected rid=%d artist=%s title=%s", result.rid, artist, title)
        return ExactTrack(result.rid, audio_url)

    @staticmethod
    def _verify_detail(html: str, artist: str, title: str) -> None:
        for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
            try:
                data = json.loads(raw)
            except ValueError:
                continue
            if data.get("@type") != "MusicRecording":
                continue
            actual_artist = (data.get("byArtist") or {}).get("name", "")
            if not _same(str(data.get("name") or ""), title) or not _same(str(actual_artist), artist):
                raise InMp3Error("歌曲详情与搜索结果不一致。")
            return
        raise InMp3Error("歌曲详情缺少可核对的歌名和歌手。")

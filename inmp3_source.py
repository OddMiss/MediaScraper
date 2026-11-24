"""Download public IN音乐网 song pages."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from inmp3_client import InMp3Client, InMp3Error
from media_types import DownloadedMedia, MediaKind, SourceError
from storage import available_path, stream_to_file

LOGGER = logging.getLogger(__name__)


class InMp3Source:
    name = "inmp3"
    hosts = {"inmp3.com", "www.inmp3.com"}
    _SONG_PATH = re.compile(r"^/song/(\d+)/?$")

    def matches(self, url: str) -> bool:
        return (urlparse(url).hostname or "").lower() in self.hosts

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        parsed = urlparse(url)
        match = self._SONG_PATH.fullmatch(parsed.path)
        if not self.matches(url) or not match:
            raise SourceError("仅支持 IN音乐网的单曲链接。")

        rid = int(match.group(1))
        try:
            LOGGER.info("IN音乐网 source download started rid=%d", rid)
            track = InMp3Client().song(rid)
            title = f"{track.artist} - {track.title}"
            target = available_path(destination, title, ".mp3")
            stream_to_file(track.audio_url, target)
            with target.open("rb") as stream:
                header = stream.read(3)
            if header != b"ID3" and not (
                len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
            ):
                target.unlink(missing_ok=True)
                raise InMp3Error("播放地址没有返回 MP3 音频。")
        except (InMp3Error, requests.RequestException, OSError) as exc:
            raise SourceError(f"IN音乐网下载失败：{exc}") from exc

        LOGGER.info("IN音乐网 source download completed rid=%d target=%s", rid, target.name)
        return [DownloadedMedia(MediaKind.AUDIO, target, title, url, "IN音乐网")]

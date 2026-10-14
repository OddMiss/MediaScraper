"""Download complete NetEase Cloud Music songs and public playlists."""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from inmp3_client import InMp3Client, InMp3Error
from media_types import DownloadedMedia, MediaKind, SourceError
from netease_client import NeteaseCloudClient, NeteaseCloudError, Song
from storage import available_path, safe_stem, stream_to_file

LOGGER = logging.getLogger(__name__)


class NeteaseMusicSource:
    name = "netease_music"
    hosts = {"music.163.com"}

    def matches(self, url: str) -> bool:
        return (urlparse(url).hostname or "").lower() in self.hosts

    @staticmethod
    def _link_target(url: str) -> tuple[str, int]:
        parsed = urlparse(url)
        # Support both current /song?id=... and older /#/song?id=... links.
        route = urlparse(parsed.fragment) if parsed.fragment.startswith("/") else parsed
        kind = route.path.strip("/").split("/")[-1]
        ids = parse_qs(route.query).get("id", [])
        if kind not in {"song", "playlist"} or not ids or not ids[0].isdigit():
            raise SourceError("仅支持网易云音乐的单曲或公开歌单链接。")
        return kind, int(ids[0])

    @staticmethod
    def _title(song: Song) -> str:
        artist = "、".join(song.artists) or "未知歌手"
        return f"{artist} - {song.title or str(song.id)}"

    def _download_song(
        self,
        client: NeteaseCloudClient,
        song: Song,
        folder: Path,
        source_url: str,
        *,
        resume_playlist: bool = False,
    ) -> DownloadedMedia | None:
        playback = client.playback(song.id)
        if playback.is_preview or (not playback.url and song.fee == 1):
            return self._download_preview(song, folder, source_url, resume_playlist=resume_playlist)
        if not playback.url:
            raise NeteaseCloudError(f"{self._title(song)} 没有可下载的完整音频。")

        title = self._title(song)
        if resume_playlist:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{safe_stem(title)}.{playback.extension}"
            if target.is_file() and target.stat().st_size > 0:
                LOGGER.info("Reusing completed playlist file target=%s", target.name)
                return DownloadedMedia(MediaKind.AUDIO, target, title, source_url, "网易云音乐")
        else:
            target = available_path(folder, title, f".{playback.extension}")
        stream_to_file(playback.url, target)
        return DownloadedMedia(MediaKind.AUDIO, target, title, source_url, "网易云音乐")

    def _download_preview(
        self, song: Song, folder: Path, source_url: str, *, resume_playlist: bool
    ) -> DownloadedMedia | None:
        title = self._title(song)
        if len(song.artists) != 1 or not song.title:
            LOGGER.info("IN音乐网 fallback skipped: non-single artist or missing title id=%s", song.id)
            return None
        try:
            match = InMp3Client().find_exact(song.artists[0], song.title)
        except (InMp3Error, requests.RequestException) as exc:
            LOGGER.warning("IN音乐网 fallback unavailable id=%s error=%s", song.id, exc)
            return None
        if match is None:
            LOGGER.info("IN音乐网 has no exact match id=%s title=%s", song.id, title)
            return None
        if resume_playlist:
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / f"{safe_stem(title)}.mp3"
            if target.is_file() and target.stat().st_size > 0:
                LOGGER.info("Reusing completed playlist file target=%s", target.name)
                return DownloadedMedia(MediaKind.AUDIO, target, title, source_url, "IN音乐网")
        else:
            target = available_path(folder, title, ".mp3")
        stream_to_file(match.audio_url, target)
        with target.open("rb") as stream:
            header = stream.read(3)
        if header != b"ID3" and not (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
            target.unlink()
            raise InMp3Error("播放地址没有返回 MP3 音频。")
        return DownloadedMedia(MediaKind.AUDIO, target, title, source_url, "IN音乐网")

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        if not self.matches(url):
            raise SourceError("不是网易云音乐链接。")
        kind, item_id = self._link_target(url)
        client = NeteaseCloudClient()
        LOGGER.info("Netease source download started kind=%s id=%s", kind, item_id)
        try:
            if kind == "song":
                song = client.song(item_id)
                downloaded = self._download_song(client, song, destination, url)
                if downloaded is None:
                    raise SourceError(f"{self._title(song)} 仅提供试听，IN音乐网未找到精确匹配的完整歌曲，已跳过下载。")
                return [downloaded]

            playlist = client.playlist(item_id)
            if not playlist.song_ids:
                raise SourceError("这个公开歌单没有歌曲。")
            folder = destination / safe_stem(playlist.title)
            media: list[DownloadedMedia] = []
            skipped_previews = 0
            for song_id in playlist.song_ids:
                song = client.song(song_id)
                downloaded = self._download_song(
                    client, song, folder, url, resume_playlist=True
                )
                if downloaded is None:
                    skipped_previews += 1
                elif downloaded.path not in {item.path for item in media}:
                    media.append(downloaded)
            if skipped_previews:
                notice = f"歌单中 {skipped_previews} 首试听歌曲未在 IN音乐网找到精确匹配，已跳过。"
                if not media:
                    raise SourceError(notice)
                media[0] = replace(media[0], notice=notice)
            LOGGER.info(
                "Netease playlist completed id=%s files=%d skipped_previews=%d",
                item_id,
                len(media),
                skipped_previews,
            )
            return media
        except (NeteaseCloudError, InMp3Error, requests.RequestException, OSError) as exc:
            raise SourceError(f"网易云音乐下载失败：{exc}") from exc

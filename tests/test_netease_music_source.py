import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from download_index import DownloadIndex
from media_types import MediaKind, SourceError
from netease_client import Playback, Playlist, Song
from netease_music_source import NeteaseMusicSource


class FakeClient:
    def song(self, song_id: int) -> Song:
        songs = {
            1: Song(1, "完整单曲", ("歌手甲",), 0),
            2: Song(2, "试听单曲", ("歌手乙",), 1),
        }
        return songs[song_id]

    def playlist(self, playlist_id: int) -> Playlist:
        assert playlist_id == 9
        return Playlist("测试歌单", (1, 2))

    def playback(self, song_id: int) -> Playback:
        if song_id == 2:
            return Playback(None, "mp3", False)
        return Playback("https://example.com/audio.mp3", "mp3", False)


def test_netease_source_skips_preview_and_names_playlist_files(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("netease_music_source.NeteaseCloudClient", FakeClient)
    monkeypatch.setattr("netease_music_source.InMp3Client", lambda: SimpleNamespace(find_exact=lambda artist, title: None))
    monkeypatch.setattr(
        "netease_music_source.stream_to_file",
        lambda url, target: target.write_bytes(b"complete audio"),
    )
    source = NeteaseMusicSource()

    assert source.matches("https://music.163.com/song?id=1")
    assert not source.matches("https://music.163.com.evil.example/song?id=1")

    with pytest.raises(SourceError, match="仅提供试听"):
        source.download("https://music.163.com/song?id=2", tmp_path)
    assert not list(tmp_path.rglob("*.mp3"))

    playlist_url = "https://music.163.com/playlist?id=9"
    media = source.download(playlist_url, tmp_path)
    assert len(media) == 1
    assert media[0].kind == MediaKind.AUDIO
    assert media[0].path.relative_to(tmp_path) == Path("测试歌单/歌手甲 - 完整单曲.mp3")
    assert "1 首试听歌曲未在 IN音乐网找到精确匹配" in (media[0].notice or "")

    index = DownloadIndex(tmp_path / "index.json")
    index.record(playlist_url, source.name, media)
    assert index.contains(playlist_url)
    payload = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert Path(payload["downloads"][playlist_url]["files"][0]) == media[0].path.relative_to(tmp_path)


def test_bot_reports_skipped_preview_in_playlist(monkeypatch, tmp_path: Path) -> None:
    import bot
    from source_registry import SourceRegistry

    monkeypatch.setattr("netease_music_source.NeteaseCloudClient", FakeClient)
    monkeypatch.setattr("netease_music_source.InMp3Client", lambda: SimpleNamespace(find_exact=lambda artist, title: None))

    def save_audio(url: str, target: Path) -> None:
        target.write_bytes(b"complete audio")

    monkeypatch.setattr("netease_music_source.stream_to_file", save_audio)
    monkeypatch.setattr(bot, "SOURCES", SourceRegistry([NeteaseMusicSource()]))
    monkeypatch.setattr(bot, "DOWNLOAD_DIR", tmp_path)
    monkeypatch.setattr(bot, "DOWNLOAD_INDEX", DownloadIndex(tmp_path / "index.json"))
    monkeypatch.setattr(bot, "ALLOWED_USER_IDS", set())
    monkeypatch.setattr(bot, "QUEUE_LOCK", asyncio.Lock())

    class Status:
        text = ""

        async def edit_text(self, text: str):
            self.text = text
            return self

    class Message:
        text = "https://music.163.com/playlist?id=9"
        message_id = 1

        def __init__(self):
            self.status = Status()

        async def reply_text(self, text: str):
            self.status.text = text
            return self.status

    message = Message()
    update = SimpleNamespace(
        effective_message=message,
        effective_user=SimpleNamespace(id=1),
        effective_chat=SimpleNamespace(id=2),
    )
    asyncio.run(bot.handle_links(update, None))

    assert "歌单中 1 首试听歌曲未在 IN音乐网找到精确匹配，已跳过" in message.status.text
    assert "测试歌单" in message.status.text


def test_netease_preview_uses_exact_inmp3_match(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("netease_music_source.NeteaseCloudClient", FakeClient)
    monkeypatch.setattr(
        "netease_music_source.InMp3Client",
        lambda: SimpleNamespace(find_exact=lambda artist, title: SimpleNamespace(audio_url="https://kw-er.kuwo.cn/test.mp3")),
    )
    monkeypatch.setattr(
        "netease_music_source.stream_to_file",
        lambda url, target: target.write_bytes(b"ID3" + b"\x00" * 32),
    )
    result = NeteaseMusicSource().download("https://music.163.com/song?id=2", tmp_path)
    assert len(result) == 1
    assert result[0].path.name == "歌手乙 - 试听单曲.mp3"
    assert result[0].provider == "IN音乐网"
    assert result[0].path.read_bytes().startswith(b"ID3")

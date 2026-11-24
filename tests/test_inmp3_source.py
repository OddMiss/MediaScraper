from pathlib import Path
from types import SimpleNamespace

import pytest

from inmp3_source import InMp3Source
from media_types import MediaKind, SourceError


def test_direct_inmp3_song_downloads_an_mp3(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "inmp3_source.InMp3Client",
        lambda: SimpleNamespace(
            song=lambda rid: SimpleNamespace(
                rid=rid,
                artist="阿梨&小花",
                title="晚风心里吹",
                audio_url="https://kw-er.kuwo.cn/resource/test.mp3",
            )
        ),
    )
    monkeypatch.setattr(
        "inmp3_source.stream_to_file",
        lambda url, target: target.write_bytes(b"ID3" + b"\0" * 32),
    )

    result = InMp3Source().download("https://inmp3.com/song/7964301", tmp_path)

    assert len(result) == 1
    assert result[0].kind == MediaKind.AUDIO
    assert result[0].provider == "IN音乐网"
    assert result[0].path.name == "阿梨&小花 - 晚风心里吹.mp3"


def test_direct_inmp3_rejects_non_song_pages(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="仅支持 IN音乐网的单曲链接"):
        InMp3Source().download("https://inmp3.com/so/test/", tmp_path)

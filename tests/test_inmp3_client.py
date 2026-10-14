import base64
from types import SimpleNamespace

from inmp3_client import InMp3Client


def _row(rid: int, title: str, artist: str, album: str = "") -> str:
    return (
        f'<div class="result-item" data-rid="{rid}"><div class="result-info">'
        f'<div class="result-title">{title}</div>'
        f'<div class="result-artist">{artist}</div>'
        f'<div class="result-album">专辑: {album}</div></div></div>'
    )


def test_first_exact_result_excludes_duet_cover_and_live(monkeypatch) -> None:
    search_html = "".join([
        _row(1, "不潮不用花钱", "林俊杰&BY2"),
        _row(2, "不潮不用花钱 (Cover)", "林俊杰"),
        _row(3, "不潮不用花钱", "林俊杰", "现场专辑"),
        _row(4, "不潮不用花钱", "林俊杰", "JJ陆"),
        _row(5, "不潮不用花钱", "林俊杰", "另一专辑"),
    ])
    audio_url = "https://kw-er.kuwo.cn/resource/test.mp3"
    code = base64.b64encode(audio_url.encode()).decode()
    detail_html = (
        '<script type="application/ld+json">'
        '{"@type":"MusicRecording","name":"不潮不用花钱",'
        '"byArtist":{"name":"林俊杰"}}</script>'
        f'<script>let code = "{code}";</script>'
    )
    requested = []

    def fake_get(url, timeout):
        requested.append(url)
        return SimpleNamespace(text=search_html if "/so/" in url else detail_html, raise_for_status=lambda: None)

    client = InMp3Client()
    monkeypatch.setattr(client.session, "get", fake_get)
    result = client.find_exact("林俊杰", "不潮不用花钱")
    assert result is not None
    assert result.rid == 4
    assert result.audio_url == audio_url
    assert requested[1].endswith("/song/4/")


def test_no_exact_result_never_opens_song_page(monkeypatch) -> None:
    client = InMp3Client()
    requested = []

    def fake_get(url, timeout):
        requested.append(url)
        return SimpleNamespace(text=_row(1, "不潮不用花钱", "林俊杰&BY2"), raise_for_status=lambda: None)

    monkeypatch.setattr(client.session, "get", fake_get)
    assert client.find_exact("林俊杰", "不潮不用花钱") is None
    assert len(requested) == 1

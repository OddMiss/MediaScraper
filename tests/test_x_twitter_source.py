from source_registry import SourceRegistry
from x_twitter_client import XTwitterClient
from x_twitter_source import XTwitterSource


def test_x_twitter_parser_selects_highest_mp4_for_each_video() -> None:
    options = [
        {
            "video_index": 1,
            "format_ext": "mp4",
            "direct_download_url": "https://video.twimg.com/low.mp4",
            "width": 320,
            "quality": 568,
            "bitrate": 600,
        },
        {
            "video_index": 1,
            "format_ext": "mp4",
            "direct_download_url": "https://video.twimg.com/high.mp4",
            "width": 1080,
            "quality": 1920,
            "bitrate": 5000,
        },
        {
            "video_index": 2,
            "format_ext": "mp4",
            "direct_download_url": "https://video.twimg.com/second.mp4",
            "width": 720,
            "quality": 1280,
            "bitrate": 2000,
        },
        {
            "video_index": 2,
            "format_ext": "m3u8",
            "direct_download_url": "https://video.twimg.com/playlist.m3u8",
            "width": 1080,
            "quality": 1920,
        },
    ]

    videos = XTwitterClient._select_videos(options)

    assert [(video.index, video.url) for video in videos] == [
        (1, "https://video.twimg.com/high.mp4"),
        (2, "https://video.twimg.com/second.mp4"),
    ]


def test_x_twitter_source_matches_only_platform_hosts() -> None:
    registry = SourceRegistry([XTwitterSource()])

    assert registry.supports("https://x.com/example/status/123?s=20")
    assert registry.supports("https://mobile.twitter.com/example/status/123")
    assert not registry.supports("https://notx.com/example/status/123")
    assert not registry.supports("https://x.com.example.org/example/status/123")
    assert registry.source_name("https://x.com/example/status/123") == "x_twitter"
    assert registry.whitelist() == ("twitter.com", "x.com")

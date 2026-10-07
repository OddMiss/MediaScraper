from pathlib import Path

from media_types import DownloadedMedia
from source_registry import SourceRegistry


class DemoSource:
    name = "demo"
    hosts = {"example.com", "short.example.com"}

    def matches(self, url: str) -> bool:
        return "example.com" in url

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        return []


def test_registry_lists_hosts_and_routes_supported_urls() -> None:
    registry = SourceRegistry([DemoSource()])

    assert registry.supports("https://short.example.com/a")
    assert not registry.supports("https://unsupported.invalid/a")
    assert registry.source_name("https://example.com/a") == "demo"
    assert registry.whitelist() == ("example.com", "short.example.com")

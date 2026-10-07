"""Select the first registered source plugin that supports a URL."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

from media_types import DownloadedMedia, MediaSource, SourceError

LOGGER = logging.getLogger(__name__)


class SourceRegistry:
    def __init__(self, sources: list[MediaSource]) -> None:
        self.sources = sources

    def supports(self, url: str) -> bool:
        return any(source.matches(url) for source in self.sources)

    def whitelist(self) -> tuple[str, ...]:
        """Domains supported by the currently registered source plugins."""
        domains = {host for source in self.sources for host in source.hosts}
        return tuple(sorted(domains))

    def source_name(self, url: str) -> str:
        """Return the registered platform name for a supported URL."""
        for source in self.sources:
            if source.matches(url):
                return source.name
        raise SourceError("暂不支持这个链接来源。")

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]:
        for source in self.sources:
            if source.matches(url):
                LOGGER.info(
                    "Routed source host=%s source=%s",
                    urlparse(url).hostname,
                    source.name,
                )
                return source.download(url, destination, title_hint)
        LOGGER.warning("No source registered for host=%s", urlparse(url).hostname)
        raise SourceError("暂不支持这个链接来源。")

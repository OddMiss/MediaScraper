"""Shared contracts for every media source plugin."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol


class MediaKind(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    TEXT = "text"


@dataclass(frozen=True)
class DownloadedMedia:
    kind: MediaKind
    path: Path
    title: str
    source_url: str
    provider: str = "未注明"
    provider_notice: str | None = None


class SourceError(RuntimeError):
    """An expected error while a source plugin is processing a URL."""


class MediaSource(Protocol):
    """A platform-specific downloader, e.g. Xiaohongshu or Bilibili."""

    name: str
    hosts: set[str]

    def matches(self, url: str) -> bool: ...

    def download(
        self, url: str, destination: Path, title_hint: str | None = None
    ) -> list[DownloadedMedia]: ...

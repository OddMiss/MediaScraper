"""Compatibility entry point for code using the original single-source API."""

from pathlib import Path

from xiaohongshu_source import XiaohongshuSource


def download_xiaohongshu(url: str, destination: str | Path) -> Path:
    return XiaohongshuSource().download(url, Path(destination))[0].path

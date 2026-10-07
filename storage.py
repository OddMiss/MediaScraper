"""Local file naming and streaming helpers shared by all source plugins."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

LOGGER = logging.getLogger(__name__)

INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_stem(title: str) -> str:
    title = INVALID_FILENAME.sub("_", title).strip(" .")
    if not title or title.upper() in RESERVED:
        title = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    return title[:180]


def available_path(destination: Path, title: str, extension: str) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    extension = extension if extension.startswith(".") else f".{extension}"
    stem = safe_stem(title)
    target = destination / f"{stem}{extension}"
    number = 1
    while target.exists():
        target = destination / f"{stem}_{number}{extension}"
        number += 1
    return target


def stream_to_file(url: str, target: Path) -> None:
    """Save a cross-origin CDN URL using the same no-Referer behavior as the web UI."""
    partial = target.with_name(f"{target.name}.part")
    bytes_written = 0
    LOGGER.info("Download started target=%s", target.name)
    try:
        with requests.get(
            url,
            stream=True,
            timeout=(15, 300),
            headers={"User-Agent": "Mozilla/5.0"},
        ) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length", "unknown")
            LOGGER.info(
                "Download response target=%s status=%s content_length=%s",
                target.name,
                response.status_code,
                content_length,
            )
            with partial.open("wb") as stream:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        stream.write(chunk)
                        bytes_written += len(chunk)
        partial.replace(target)
        LOGGER.info("Download completed target=%s bytes=%d", target.name, bytes_written)
    except Exception:
        if partial.exists():
            partial.unlink()
        LOGGER.exception("Download failed target=%s bytes_written=%d", target.name, bytes_written)
        raise

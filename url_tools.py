"""Extract user-posted HTTP(S) URLs without relying on Telegram entities."""

from __future__ import annotations

import re

URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?，。；：！？）】》」』'\""
TITLE_HINT_PATTERN = re.compile(r"【([^【】]+)】")


def extract_urls(text: str) -> list[str]:
    """Return unique URLs in their original order."""
    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_PATTERN.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        if url and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def title_hint_before_url(text: str, url: str) -> str | None:
    """Use the final 【…】 label before a link on the same shared-text line."""
    position = text.find(url)
    if position < 0:
        return None
    line_start = max(text.rfind("\n", 0, position), text.rfind("\r", 0, position)) + 1
    labels = TITLE_HINT_PATTERN.findall(text[line_start:position])
    return labels[-1].strip() if labels else None

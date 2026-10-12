"""Small state holder used to detect a stalled Telegram polling task."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass
class PollingHealth:
    """Track completed or failed ``getUpdates`` calls using a monotonic clock."""

    last_activity: float = field(default_factory=monotonic)
    restart_requested: bool = False

    def record_activity(self, now: float | None = None) -> None:
        self.last_activity = monotonic() if now is None else now

    def is_stalled(self, timeout_seconds: float, now: float | None = None) -> bool:
        current_time = monotonic() if now is None else now
        return current_time - self.last_activity >= timeout_seconds

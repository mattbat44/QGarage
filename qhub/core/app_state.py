from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional


class AppState(Enum):
    """Lifecycle states for a QHub app."""

    DISCOVERED = auto()
    LOADING = auto()
    READY = auto()
    RUNNING = auto()
    ERROR = auto()
    CRASHED = auto()
    DISABLED = auto()
    INSTALLING = auto()


MAX_CONSECUTIVE_ERRORS = 3
MAX_ERROR_LOG_SIZE = 50


@dataclass
class AppHealth:
    """Tracks health and error history for a single app."""

    state: AppState = AppState.DISCOVERED
    consecutive_errors: int = 0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    error_log: deque = field(default_factory=lambda: deque(maxlen=MAX_ERROR_LOG_SIZE))

    def record_success(self) -> None:
        self.state = AppState.READY
        self.consecutive_errors = 0

    def record_error(self, error_msg: str) -> None:
        self.consecutive_errors += 1
        self.last_error = error_msg
        self.last_error_time = datetime.now()
        # deque with maxlen automatically handles overflow
        self.error_log.append(f"[{self.last_error_time.isoformat()}] {error_msg}")

        if self.consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            self.state = AppState.CRASHED
        else:
            self.state = AppState.ERROR

    def reset(self) -> None:
        """Manual reset — allows retrying a crashed app."""
        self.state = AppState.DISCOVERED
        self.consecutive_errors = 0
        self.last_error = None

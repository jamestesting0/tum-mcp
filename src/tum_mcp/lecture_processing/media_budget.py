"""Per-recording transfer accounting and cooperative cancellation."""

import threading

from tum_mcp.errors import CampusError, Code


class TransferBudget:
    """Mutable byte accounting shared by at most four transfer threads."""

    def __init__(self, limit: int = 8 * 1024**3) -> None:
        self.limit, self.used = limit, 0
        self.lock, self.cancelled = threading.Lock(), threading.Event()

    def charge(self, size: int) -> None:
        with self.lock:
            if self.used + size > self.limit:
                raise CampusError(
                    Code.CAPABILITY_UNSUPPORTED,
                    "Media transfer byte budget exhausted; resume later.",
                )
            self.used += size

    def check(self) -> None:
        if self.cancelled.is_set():
            raise KeyboardInterrupt

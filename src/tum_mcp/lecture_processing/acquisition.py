"""Within-run segment reuse with a shared recording budget."""

import hashlib

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.media import AcquiredSegment, MediaCache, acquire
from tum_mcp.lecture_processing.media_models import Manifest
from tum_mcp.lecture_processing.progress import disk_guard
from tum_mcp.lecture_processing.validity import Validity


class Acquisition:
    def __init__(self, manifest: Manifest, cache: MediaCache, valid: Validity) -> None:
        self.manifest, self.cache, self.valid = manifest, cache, valid
        self.loaded: dict[int, AcquiredSegment] = {}

    @property
    def content_revision(self) -> str:
        identity = "\n".join(
            f"{key}:{item.sha256}:{item.initialization_sha256}"
            for key, item in sorted(self.loaded.items())
        )
        return hashlib.sha256(identity.encode()).hexdigest()

    def span(self, span: Interval) -> tuple[AcquiredSegment, ...]:
        disk_guard(self.cache.root.parent, reserve=1024**3)
        indexes = [
            i
            for i, item in enumerate(self.manifest.segments)
            if item.span.start_s < span.end_s and span.start_s < item.span.end_s
        ]
        if not indexes:
            raise CampusError(
                Code.INVALID_RESPONSE, "No media covers this requested original time."
            )
        # Neighbor fragments carry AAC packets straddling video-fragment boundaries.
        selected = self.manifest.segments[
            max(0, indexes[0] - 1) : min(len(self.manifest.segments), indexes[-1] + 2)
        ]
        unseen = tuple(item for item in selected if item.sequence not in self.loaded)
        if unseen:
            try:
                acquired = acquire(Manifest(segments=unseen), self.cache, self.valid)
            except CampusError:
                # Transfer workers are reaped before acquire exits; a budget/error is a
                # partial-result condition, distinct from the user's KeyboardInterrupt.
                self.cache.client.budget.cancelled.clear()
                raise
            for item in acquired:
                self.loaded[item.segment.sequence] = item
        return tuple(
            self.loaded[item.sequence] for item in selected if item.sequence in self.loaded
        )

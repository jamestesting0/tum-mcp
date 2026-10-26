"""Confined, content-verified VOD cache and four-way recording acquisition."""

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.media_models import (
    CacheEntry,
    Manifest,
    MediaRef,
    Segment,
)
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen
from tum_mcp.study_store import confined


class CachedMedia(Frozen):
    path: Path
    entry: CacheEntry
    reused: bool
    server_validated: bool


class AcquiredSegment(Frozen):
    segment: Segment
    path: Path
    sha256: str
    initialization: Path | None = None
    initialization_sha256: str | None = None
    retained: tuple[Interval, ...]


class MediaCache:
    """Mutable owned-file accounting; user files and selected figures live elsewhere."""

    def __init__(self, root: Path, client: MediaHTTP, limit: int = 10 * 1024**3) -> None:
        if root.is_symlink() or root.is_junction():
            raise CampusError(
                Code.WORKSPACE_CONFLICT, "Private media cache cannot be a symbolic path."
            )
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root, self.client, self.limit = root, client, limit
        self.lock = threading.Lock()
        self.protected: set[str] = set()
        self.reused = 0
        self.used = sum(
            confined(root, p.name).stat().st_size
            for p in root.glob("*.bin")
            if re.fullmatch(r"[a-f0-9]{64}\.bin", p.name)
        )

    def _read(self, key: str) -> CacheEntry | None:
        metadata, body = confined(self.root, f"{key}.json"), confined(self.root, f"{key}.bin")
        if not metadata.is_file() or not body.is_file():
            return None
        if metadata.stat().st_size > 16384 or body.stat().st_size > 64 * 1024 * 1024:
            raise CampusError(Code.INVALID_RESPONSE, "Media cache entry exceeds its bound.")
        try:
            entry = CacheEntry.model_validate_json(metadata.read_bytes())
            with body.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if entry.key == key and entry.size == body.stat().st_size and actual == entry.sha256:
                return entry
        except ValidationError:
            raise CampusError(
                Code.INVALID_RESPONSE, "Media cache metadata is invalid; preserve and inspect it."
            ) from None
        return None

    def _make_room(self, extra: int) -> None:
        for body in sorted(self.root.glob("*.bin"), key=lambda p: p.lstat().st_mtime):
            if self.used + extra <= self.limit:
                return
            key = body.stem
            if key in self.protected or re.fullmatch(r"[a-f0-9]{64}", key) is None:
                continue
            safe = confined(self.root, body.name)
            size = safe.stat().st_size
            safe.unlink()
            confined(self.root, f"{key}.json").unlink(missing_ok=True)
            self.used -= size
        if self.used + extra > self.limit:
            raise CampusError(
                Code.CAPABILITY_UNSUPPORTED,
                "Private media cache budget exhausted; checkpoint retained.",
            )

    def get(self, ref: MediaRef, *, revalidate: bool = True) -> CachedMedia:
        self.client.budget.check()
        key = ref.key
        with self.lock:
            self.protected.add(key)
            previous = self._read(key)
        path = confined(self.root, f"{key}.bin")
        if previous is not None and not revalidate:
            with self.lock:
                self.reused += 1
            return CachedMedia(path=path, entry=previous, reused=True, server_validated=False)
        fetched = self.client.get(ref, previous)
        if fetched.unchanged:
            if previous is None:
                raise CampusError(
                    Code.INVALID_RESPONSE, "Unchanged media lacks a verified cache entry."
                )
            with self.lock:
                self.reused += 1
            return CachedMedia(path=path, entry=previous, reused=True, server_validated=True)
        entry = CacheEntry(
            key=key,
            sha256=hashlib.sha256(fetched.body).hexdigest(),
            size=len(fetched.body),
            etag=fetched.etag,
            modified=fetched.modified,
        )
        with self.lock:
            old_size = path.stat().st_size if path.is_file() else 0
            self._make_room(max(0, entry.size - old_size))
            if previous is None or previous.sha256 != entry.sha256:
                private_write(path, fetched.body)
            private_write(confined(self.root, f"{key}.json"), entry.model_dump_json().encode())
            self.used += entry.size - old_size
            reused = previous is not None and previous.sha256 == entry.sha256
            self.reused += int(reused)
        return CachedMedia(path=path, entry=entry, reused=reused, server_validated=True)


def acquire(
    manifest: Manifest, cache: MediaCache, validity: Validity
) -> tuple[AcquiredSegment, ...]:
    """Fetch only intersecting segments once; keep original segment time on every result."""
    require_content(validity)
    selected = tuple(
        segment
        for segment in manifest.segments
        if any(
            segment.span.start_s < span.end_s and span.start_s < segment.span.end_s
            for span in validity.eligible
        )
    )
    references = {
        ref.key: ref
        for segment in selected
        for ref in (segment.media, segment.initialization)
        if ref is not None
    }
    with cache.lock:
        cache.protected.update(references)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="lecture-media") as workers:
        futures = [workers.submit(cache.get, ref) for ref in references.values()]
        results: list[CachedMedia] = []
        try:
            for future in as_completed(futures):
                results.append(future.result())
        finally:
            if len(results) != len(futures):
                cache.client.budget.cancelled.set()
                for future in futures:
                    future.cancel()
    entries = {item.entry.key: item for item in results}
    return tuple(
        AcquiredSegment(
            segment=segment,
            path=entries[segment.media.key].path,
            sha256=entries[segment.media.key].entry.sha256,
            initialization=entries[segment.initialization.key].path
            if segment.initialization
            else None,
            initialization_sha256=(
                entries[segment.initialization.key].entry.sha256 if segment.initialization else None
            ),
            retained=tuple(
                Interval(
                    start_s=max(segment.span.start_s, span.start_s),
                    end_s=min(segment.span.end_s, span.end_s),
                )
                for span in validity.eligible
                if max(segment.span.start_s, span.start_s) < min(segment.span.end_s, span.end_s)
            ),
        )
        for segment in selected
    )

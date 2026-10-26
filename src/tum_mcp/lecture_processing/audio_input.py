"""Join complete local fragments in one timestamp period to preserve AAC boundaries."""

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.decoding import LocalInput, verify_segment
from tum_mcp.lecture_processing.media import AcquiredSegment


def periods(segments: tuple[AcquiredSegment, ...]) -> tuple[tuple[AcquiredSegment, ...], ...]:
    result: list[list[AcquiredSegment]] = []
    for item in segments:
        if (
            not result
            or result[-1][-1].segment.discontinuity != item.segment.discontinuity
            or result[-1][-1].initialization_sha256 != item.initialization_sha256
        ):
            result.append([])
        result[-1].append(item)
    return tuple(tuple(group) for group in result)


@contextmanager
def joined_input(segments: tuple[AcquiredSegment, ...], directory: Path) -> Iterator[LocalInput]:
    if sum(item.path.stat().st_size for item in segments) > 512 * 1024**2:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "One audio period exceeds the 512 MiB working bound."
        )
    for item in segments:
        verify_segment(item)
    first = segments[0]
    with tempfile.TemporaryDirectory(prefix="input-", dir=directory) as folder:
        path = Path(folder) / ("audio.mp4" if first.initialization else "audio.ts")
        with path.open("wb") as output:
            sources = ((first.initialization,) if first.initialization else ()) + tuple(
                item.path for item in segments
            )
            for source in sources:
                with source.open("rb") as stream:
                    shutil.copyfileobj(stream, output)
        yield LocalInput(path=path, format="mov" if first.initialization else "mpegts")

"""Confirm recording figures against prepared captures and reproducible pixel transforms."""

import tempfile
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_content import Lecture
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import evidence_bytes
from tum_mcp.lecture_processing.visuals import app_frame
from tum_mcp.study_store import ReadObserver, digest, private_path


def verify_figures(
    root: Path, lecture: Lecture, *, read_observer: ReadObserver | None = None
) -> None:
    figures = tuple(figure for section in lecture.sections for figure in section.figures)
    if lecture.recording.synthetic or not figures:
        return
    try:
        inventory = FrameInventory.model_validate_json(
            evidence_bytes(root, lecture.recording.key, "frames.json", read_observer=read_observer)
        )
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Prepared frame inventory is malformed.") from None
    for figure in figures:
        verified = False
        for frame in inventory.captured:
            if frame.captured_at_s != figure.captured_at_s:
                continue
            path = private_path(root, f"lectures/{lecture.recording.key}/frames/{frame.sha256}.png")
            if not path.is_file() or path.stat().st_size > 64 * 1024**2:
                raise CampusError(
                    Code.STALE_RESULT, "Prepared original frame is missing or changed."
                )
            body = path.read_bytes()
            if read_observer is not None:
                read_observer(path, body)
            if digest(body) != frame.sha256:
                raise CampusError(
                    Code.STALE_RESULT, "Prepared original frame is missing or changed."
                )
            if figure.crop is None and figure.sha256 == frame.sha256:
                verified = True
                break
            with tempfile.TemporaryDirectory(prefix="lecture-figure-check-") as folder:
                derived = app_frame(
                    frame.model_copy(update={"path": path}), Path(folder), figure.crop
                )
                if derived.sha256 == figure.sha256:
                    verified = True
                    break
        if not verified:
            raise CampusError(
                Code.STALE_RESULT,
                "A lecture figure does not match a prepared recording capture or verified crop.",
            )

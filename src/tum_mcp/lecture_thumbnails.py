"""Confirm highlight thumbnails against prepared captures and reproducible pixel transforms."""

import tempfile
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_content import Lecture
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import evidence_bytes
from tum_mcp.lecture_processing.visuals import app_frame
from tum_mcp.study_store import digest, private_path


def verify_thumbnails(root: Path, lecture: Lecture) -> None:
    if lecture.recording.synthetic:
        return
    if not lecture.images:
        return
    try:
        inventory = FrameInventory.model_validate_json(
            evidence_bytes(root, lecture.recording.key, "frames.json")
        )
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Prepared frame inventory is malformed.") from None
    for thumbnail in lecture.images:
        verified = False
        for frame in inventory.captured:
            if frame.captured_at_s != thumbnail.captured_at_s:
                continue
            path = private_path(root, f"lectures/{lecture.recording.key}/frames/{frame.sha256}.png")
            if (
                not path.is_file()
                or path.stat().st_size > 64 * 1024**2
                or digest(path.read_bytes()) != frame.sha256
            ):
                raise CampusError(
                    Code.STALE_RESULT, "Prepared original frame is missing or changed."
                )
            if thumbnail.crop is None and thumbnail.sha256 == frame.sha256:
                verified = True
                break
            with tempfile.TemporaryDirectory(prefix="lecture-thumbnail-check-") as folder:
                derived = app_frame(
                    frame.model_copy(update={"path": path}), Path(folder), thumbnail.crop
                )
                if derived.sha256 == thumbnail.sha256:
                    verified = True
                    break
        if not verified:
            raise CampusError(
                Code.STALE_RESULT,
                "A highlight thumbnail does not match a prepared recording capture or its "
                "verified crop. Stage it again with tum-mcp lecture thumbnail.",
            )

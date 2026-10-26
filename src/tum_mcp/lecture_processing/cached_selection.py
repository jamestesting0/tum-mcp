"""Preserve prior explicit caption imports and critical frame selections on update."""

from pathlib import Path

from pydantic import ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_processing.prepare_visuals import FrameInventory
from tum_mcp.lecture_processing.receipts import RECEIPT, PreparedReceipt
from tum_mcp.lecture_processing.validity import Validity, require_content
from tum_mcp.study_store import confined, digest


def previous_selection(
    directory: Path,
    valid: Validity,
    revision: str,
    imported: Path | None,
    targets: tuple[float, ...],
) -> tuple[Path | None, tuple[float, ...]]:
    require_content(valid)
    receipt_path = confined(directory, "receipt.json")
    if not receipt_path.is_file():
        return imported, targets
    if receipt_path.stat().st_size > 1024**2:
        raise CampusError(Code.INVALID_RESPONSE, "Prior lecture receipt exceeds its bound.")
    try:
        previous = RECEIPT.validate_json(receipt_path.read_bytes())
        if not isinstance(previous, PreparedReceipt):
            return imported, targets
        if imported is None and previous.imported_transcript_sha256 is not None:
            path = confined(directory, "imported.vtt")
            if (
                not path.is_file()
                or path.stat().st_size > 10 * 1024**2
                or digest(path.read_bytes()) != previous.imported_transcript_sha256
            ):
                raise CampusError(
                    Code.STALE_RESULT,
                    "Cached imported captions changed; provide their verified replacement.",
                )
            imported = path
        if previous.metadata_revision == revision:
            path = confined(directory, "frames.json")
            if (
                not path.is_file()
                or path.stat().st_size > 16 * 1024**2
                or digest(path.read_bytes()) != previous.frames_sha256
            ):
                raise CampusError(
                    Code.STALE_RESULT,
                    "Prior frame selection changed; reconcile its evidence first.",
                )
            inventory = FrameInventory.model_validate_json(path.read_bytes())
            targets = tuple(
                sorted(
                    set(targets)
                    | {
                        frame.requested_at_s
                        if frame.requested_at_s is not None
                        else frame.captured_at_s
                        for frame in inventory.captured
                    }
                )
            )
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Prior lecture selection is malformed; preserve and inspect it."
        ) from None
    return imported, targets

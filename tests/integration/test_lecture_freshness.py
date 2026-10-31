import json
import shutil
from pathlib import Path

import pytest
from lecture_prepared_fixture import prepare_recording
from PIL import Image

from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing.receipts import InvalidReceipt
from tum_mcp.study_build import build
from tum_mcp.study_store import digest


@pytest.mark.parametrize("failure", ["whole_silence", "invented_frame", "generated_diagram"])
def test_invalid_recording_or_frame_blocks_new_build_before_source_sync(
    tmp_path: Path, failure: str, lecture_extension: Path
) -> None:
    prepared = prepare_recording(tmp_path)
    root, notes = prepared.root, prepared.notes
    build(root, publish=False)
    previous = (root / "app/data.mjs").read_bytes()
    thumbnail = notes["lectures"][0]["highlights"][0]["thumbnail"]
    if failure == "whole_silence":
        invalid = InvalidReceipt(
            key=prepared.recording.key,
            course_id=42,
            recording_id=11,
            checked_at="2026-10-26T11:00:00Z",
            reason="whole_recording_silence",
            duration_s=600,
        )
        (prepared.folder / "receipt.json").write_text(invalid.model_dump_json())
    elif failure == "invented_frame":
        thumbnail["captured_at_s"] = 37.55
        prepared.write_notes()
    else:
        forged = tmp_path / "generated.png"
        with Image.new("RGB", (640, 360), "red") as image:
            image.save(forged)
        thumbnail["sha256"] = digest(forged.read_bytes())
        thumbnail["asset"] = f"lecture-assets/{thumbnail['sha256']}.png"
        shutil.copy2(forged, root / ".tum-mcp" / thumbnail["asset"])
        prepared.write_notes()
    # The ordinary source inventory remains unchanged, but the latest private validity wins.
    with pytest.raises(CampusError):
        build(root, publish=False)
    assert (root / "app/data.mjs").read_bytes() == previous
    assert json.loads(prepared.notes_path.read_text()) == notes

from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from tum_mcp.course.lecture.data import read_lectures
from tum_mcp.course.project.models import Key, StudyState
from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError
from tum_mcp.lecture_processing.receipts import (
    InvalidReceipt,
    Receipt,
    read_receipt,
    require_current_receipt,
)
from tum_mcp.settings import Frozen

RecordingKey = Annotated[str, Field(pattern=r"^live-[1-9][0-9]*-[1-9][0-9]*$")]


class Exclusion(Frozen):
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    duplicate_of: RecordingKey | None = None


class LectureScope(Frozen):
    through: date
    exclusions: dict[RecordingKey, Exclusion] = Field(default_factory=dict)

    @model_validator(mode="after")
    def distinct_duplicates(self) -> "LectureScope":
        if any(key == value.duplicate_of for key, value in self.exclusions.items()):
            raise ValueError("A duplicate must refer to another recording.")
        return self


class RecordingRow(Frozen):
    recording: RecordingKey
    recorded_on: date | None
    as_of: str
    evidence: Literal["prepared", "partial", "invalid", "unavailable"]
    membership: Literal["selected", "after_cutoff", "excluded", "undetermined"]
    output: Literal["authored", "checkpoint_only", "no_page"]
    authored_key: Key | None
    reason: str | None = None
    exclusion: Exclusion | None = None


def cached_recordings(root: Path, state: StudyState) -> list[Receipt]:
    directory = private_path(root, "lectures")
    return [
        read_receipt(root, path.parent.name, state=state)
        for path in sorted(directory.glob("live-*/receipt.json"))
    ]


def accounting(
    root: Path,
    receipts: list[Receipt],
    through: date,
    items: tuple[str, ...],
    scope: LectureScope | None,
) -> tuple[list[RecordingRow], list[str]]:
    content = read_lectures(root)
    pages = {item.recording.key: item.key for item in content.lectures} if content else {}
    keys = {receipt.key for receipt in receipts}
    rows: list[RecordingRow] = []
    problems: list[str] = []
    exclusions = scope.exclusions if scope else {}
    for key in exclusions:
        if key not in keys:
            problems.append(f"Lecture exclusion {key} references an unknown recording.")
    for receipt in receipts:
        day = (
            receipt.recorded_on
            if isinstance(receipt, InvalidReceipt)
            else receipt.recording.recorded_on
        )
        reason = receipt.reason if isinstance(receipt, InvalidReceipt) else None
        evidence = receipt.status
        if not isinstance(receipt, InvalidReceipt):
            try:
                require_current_receipt(root, receipt)
            except CampusError as error:
                evidence, reason = "unavailable", error.message
        page = pages.get(receipt.key)
        selected = f"lecture/{page or receipt.key}" in items
        exclusion = exclusions.get(receipt.key)
        if day and day > through:
            membership = "after_cutoff"
        elif exclusion:
            membership = "excluded"
        elif selected:
            membership = "selected"
        else:
            membership = "undetermined"
        if scope and selected and membership != "selected":
            problems.append(f"Lecture {receipt.key} is selected and {membership}.")
        if scope and membership == "undetermined" and evidence != "invalid":
            problems.append(
                f"Account for lecture {receipt.key} in the batch or record its exclusion."
            )
        checkpoint = private_path(root, f"work/lecture-selection/{receipt.key}.json")
        rows.append(
            RecordingRow(
                recording=receipt.key,
                recorded_on=day,
                as_of=receipt.checked_at,
                evidence=evidence,
                membership=membership,
                authored_key=page,
                output="authored"
                if page
                else "checkpoint_only"
                if checkpoint.is_file()
                else "no_page",
                reason=reason,
                exclusion=exclusion,
            )
        )
    retained = {
        row.recording
        for row in rows
        if row.membership == "selected" and row.evidence in {"prepared", "partial"}
    }
    for key, exclusion in exclusions.items():
        if exclusion.duplicate_of and exclusion.duplicate_of not in retained:
            problems.append(
                f"Lecture {key}: select a usable original in place of {exclusion.duplicate_of}."
            )
    return rows, problems

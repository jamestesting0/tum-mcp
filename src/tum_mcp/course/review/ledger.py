"""Review records: per item, the verdict of every check and every finding with its lifecycle.

Scores are never typed: each dimension scores the lowest open or kept finding it owns, else 3.
"""

import re
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, ValidationError, model_validator

from tum_mcp.course.content.study import Text
from tum_mcp.course.project.store import Write, apply, confined, private_name, read_bytes
from tum_mcp.course.review.models import Check, VisualReview
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
FindingId = Annotated[str, Field(pattern=r"^F\d+$")]
LIVE = frozenset({"open", "fixed", "reopened"})


class ClosestCall(Frozen):
    quote: Text
    location: Annotated[str, Field(min_length=1, max_length=300)]
    reason: Text


class Verdict(Frozen):
    verdict: Literal["pass", "fail", "uncertain"]
    method: Text
    round: int = Field(ge=0)
    provenance: Literal["fresh", "same", "provisional", "code", "user"]
    fingerprint: Fingerprint
    covers: tuple[str, ...] = Field(default=("*",), min_length=1, max_length=200)
    version: int = Field(ge=1)
    closest: ClosestCall | None = None
    evidence: Text | None = None


class Finding(Frozen):
    id: FindingId
    check: Check
    quote: Text
    location: Annotated[str, Field(min_length=1, max_length=300)]
    why: Text
    fix: Text
    score: Literal[1, 2] = 2
    source: Literal["checker", "user", "report"] = "checker"
    status: Literal["open", "fixed", "verified", "reopened", "rejected", "kept"] = "open"
    reason: Text | None = None
    opened: int = Field(ge=0)
    closed: int | None = None
    block: str
    blocks_at_open: dict[str, Fingerprint] = Field(default_factory=dict)
    reopens: int = Field(default=0, ge=0)
    late: bool = False

    @property
    def dimension(self) -> str:
        return self.check.split(".")[0]

    @model_validator(mode="after")
    def explained(self) -> "Finding":
        if self.status in {"rejected", "kept"} and not self.reason:
            raise ValueError("A rejected or kept finding says why.")
        if self.status == "kept" and self.score == 1:
            raise ValueError("A finding that blocks learning is fixed, never kept.")
        return self


class Ruling(Frozen):
    """A checker's ruling on one advisory flag: a finding opened for it, or why it does not
    apply here. It holds while the item's content is unchanged."""

    ruling: Literal["finding", "not_applicable"]
    reason: Text
    round: int = Field(ge=0)
    provenance: Literal["fresh", "same", "provisional", "code", "user"]
    fingerprint: Fingerprint


class RoundEntry(Frozen):
    round: int = Field(ge=0)
    scores: dict[str, int]
    opened: int = Field(default=0, ge=0)
    closed: int = Field(default=0, ge=0)


class ItemRecord(Frozen):
    schema_version: Literal[2] = 2
    item: Annotated[str, Field(min_length=1, max_length=200)]
    checks: dict[Check, Verdict] = Field(default_factory=dict)
    findings: tuple[Finding, ...] = Field(default=(), max_length=500)
    visuals: tuple[VisualReview, ...] = Field(default=(), max_length=200)
    visuals_fingerprint: Fingerprint | None = None
    history: tuple[RoundEntry, ...] = Field(default=(), max_length=500)
    # Keyed `flag@where`, for the advisory flags that need a checker's ruling.
    rulings: dict[str, Ruling] = Field(default_factory=dict)

    def scores(self, dimensions: tuple[str, ...]) -> dict[str, int]:
        result = {name: 3 for name in dimensions}
        for finding in self.findings:
            if finding.dimension in result and (finding.status in LIVE or finding.status == "kept"):
                result[finding.dimension] = min(result[finding.dimension], finding.score)
        if self.visuals and "representation" in result:
            weakest = min(min(visual.scores.values()) for visual in self.visuals)
            result["representation"] = min(result["representation"], weakest)
        return result


def record_name(key: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9/_.-]*", key) or ".." in key:
        raise CampusError(Code.INVALID_RESPONSE, f"Unsafe review item key {key}.")
    return private_name(Path("."), f"review/items/{key}.json")


def read_record(root: Path, key: str) -> ItemRecord:
    body = read_bytes(confined(root, record_name(key)))
    if body is None:
        return ItemRecord(item=key)
    try:
        record = ItemRecord.model_validate_json(body)
    except ValidationError as error:
        where = ", ".join(".".join(map(str, e["loc"])) for e in error.errors(include_input=False))
        raise CampusError(
            Code.INVALID_RESPONSE, f"Invalid review record {record_name(key)} at: {where[:300]}."
        ) from None
    if record.item != key:
        raise CampusError(Code.INVALID_RESPONSE, f"{record_name(key)} holds another item.")
    return record


def record_write(root: Path, record: ItemRecord) -> Write:
    name = record_name(record.item)
    return Write(
        name, read_bytes(confined(root, name)), (record.model_dump_json(indent=2) + "\n").encode()
    )


def save(root: Path, records: list[ItemRecord]) -> None:
    apply(root, tuple(record_write(root, record) for record in records))

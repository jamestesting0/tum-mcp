"""Source digests: what one source teaches, read once and reused by plans, authors and checkers.

A digest lives at `.tum-mcp/digests/<source>.json` and names the source version it was read
from; a changed source makes it stale. Its pages must exist in the source's read text.
"""

import re
from pathlib import Path

from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.content.study import Text
from tum_mcp.course.project.models import Digest, Key, PageRange, ResourceState, StudyState
from tum_mcp.course.project.store import confined, digest, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


class Entry(Frozen):
    pages: PageRange
    text: Text


class SourceDigest(Frozen):
    source: Key
    sha256: Digest
    outcomes: tuple[Text, ...] = Field(default=(), max_length=60)
    examples: tuple[Entry, ...] = Field(default=(), max_length=120)
    definitions: tuple[Entry, ...] = Field(default=(), max_length=200)
    figures: tuple[Entry, ...] = Field(default=(), max_length=120)


def read_digest(root: Path, source: str) -> SourceDigest | None:
    body = read_bytes(confined(root, f".tum-mcp/digests/{source}.json"))
    if body is None:
        return None
    try:
        return SourceDigest.model_validate_json(body)
    except ValidationError as error:
        raise CampusError(
            Code.INVALID_RESPONSE, f"Digest {source}: {error.errors()[0]['msg']}"
        ) from None


def digest_status(root: Path, state: StudyState) -> list[dict[str, JsonValue]]:
    """Each current source with its digest: missing, stale, or current with any page that
    lies past the source's read text."""
    return [
        digest_evidence(root, item.resource.key, item, read_digest(root, item.resource.key))
        for item in state.resources
    ]


def digest_evidence(
    root: Path, source: str, item: ResourceState | None, found: SourceDigest | None
) -> dict[str, JsonValue]:
    from tum_mcp.course.sources.text import cached_record

    row: dict[str, JsonValue] = {
        "source": source,
        "status": "missing" if found is None else "unavailable",
        "availability": "unknown" if item is None else "unavailable",
        "locator_status": "unverified",
    }
    if item is None or item.status != "current" or item.sha256 is None or item.path is None:
        return row
    body = read_bytes(confined(root, item.path))
    if body is None:
        return row
    row["availability"] = "available"
    if found is None:
        return row
    if found.sha256 != item.sha256 or digest(body) != item.sha256:
        row["status"] = "stale"
        return row
    row["status"] = "current"
    record = cached_record(root, item.sha256)
    if record and record.pages:
        outside: list[JsonValue] = sorted(
            {
                entry.pages
                for entry in (*found.examples, *found.definitions, *found.figures)
                if int(entry.pages.rpartition("-")[2]) > len(record.pages)
            }
        )
        row["locator_status"] = "invalid" if outside else "in_bounds"
        if outside:
            row["pages_outside"] = outside
    return row


_WORD = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.casefold()) if len(word) > 3}


def definition_flags(root: Path, state: StudyState, content, exam) -> list[dict[str, JsonValue]]:
    """A Study or cheatsheet definition shorter than the fullest one a current digest gives for
    the same term: the course states conditions the item leaves out."""
    stated: list[tuple[str, str, str]] = []
    for item in state.resources:
        if item.status != "current" or not item.sha256:
            continue
        found = read_digest(root, item.resource.key)
        if found is not None and found.sha256 == item.sha256:
            stated += [(item.resource.key, e.pages, e.text) for e in found.definitions]
    targets: list[tuple[str, str, str]] = []
    for unit in content.units if content else ():
        targets += [
            (f"{unit.key}#{index}", block.term, block.statement)
            for index, block in enumerate(unit.blocks)
            if block.kind == "definition"
        ]
    for concept in exam.concepts if exam else ():
        if concept.kind == "definition":
            targets.append((f"concept:{concept.key}", concept.title, concept.line))
    flags: list[dict[str, JsonValue]] = []
    for where, term, statement in targets:
        subject = re.compile(rf"^(?:an?|the)?\s*{re.escape(term)}\b", re.IGNORECASE)
        fuller = [
            (source, pages, text)
            for source, pages, text in stated
            if subject.match(text)
            and len(text) >= 1.4 * len(statement)
            and len(_words(text) - _words(statement) - _words(term)) >= 4
        ]
        if fuller:
            source, pages, text = max(fuller, key=lambda entry: len(entry[2]))
            flags.append(
                {
                    "item": where,
                    "flag": "definition_refined",
                    "detail": f"The course defines '{term}' more fully ({source}, p. {pages}): "
                    f"'{text[:220]}'. State that form, or keep this one with the reason.",
                }
            )
    return flags

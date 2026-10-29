"""Report duplicate course materials across providers without merging or deleting files."""

import hashlib
import heapq
import re
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel

from tum_mcp.errors import CampusError
from tum_mcp.study_models import ResourceState, StudyState
from tum_mcp.study_text import document_text

SKETCH = 128
SHINGLE = 5
NEAR_THRESHOLD = 0.6
MIN_SHINGLES = 20
# Lower rank is preferred: official campus copies, then the user's own files.
_PREFERENCE = {"moodle": 0, "artemis": 0, "tum_live": 0, "zulip": 1, "local": 2}


class ExactGroup(BaseModel):
    sha256: str
    keys: tuple[str, ...]
    preferred: str


class NearPair(BaseModel):
    left: str
    right: str
    similarity: float


class DuplicateReport(BaseModel):
    exact: tuple[ExactGroup, ...]
    near: tuple[NearPair, ...] = ()
    needs_visual: tuple[str, ...] = ()
    unreadable: tuple[str, ...] = ()


def _rank(state: StudyState, item: ResourceState) -> tuple[int, str]:
    providers = {binding.key: binding.provider for binding in state.course.bindings}
    return (_PREFERENCE.get(providers.get(item.resource.binding, ""), 1), item.resource.key)


def exact_groups(state: StudyState) -> tuple[ExactGroup, ...]:
    by_hash: dict[str, list[ResourceState]] = defaultdict(list)
    for item in state.resources:
        if item.status == "current" and item.sha256:
            by_hash[item.sha256].append(item)
    groups = []
    for sha256, items in sorted(by_hash.items()):
        if len(items) > 1:
            ordered = sorted(items, key=lambda item: _rank(state, item))
            groups.append(
                ExactGroup(
                    sha256=sha256,
                    keys=tuple(sorted(item.resource.key for item in items)),
                    preferred=ordered[0].resource.key,
                )
            )
    return tuple(groups)


def _sketch(text: str) -> frozenset[int] | None:
    """Bottom-k sketch: the SKETCH smallest shingle hashes estimate Jaccard similarity."""
    words = re.findall(r"[^\W_]+", text.casefold())
    shingles = {" ".join(words[i : i + SHINGLE]) for i in range(len(words) - SHINGLE + 1)}
    if len(shingles) < MIN_SHINGLES:
        return None
    hashes = (
        int.from_bytes(hashlib.blake2b(item.encode(), digest_size=8).digest(), "big")
        for item in shingles
    )
    return frozenset(heapq.nsmallest(SKETCH, hashes))


def _similarity(left: frozenset[int], right: frozenset[int]) -> float:
    union = heapq.nsmallest(SKETCH, left | right)
    return sum(value in left and value in right for value in union) / len(union)


def near_candidates(
    root: Path, state: StudyState, kinds: frozenset[str] = frozenset({"exam", "exercise"})
) -> DuplicateReport:
    """Find likely copies of the same document (re-uploads, re-exports, solutions)."""
    exact = exact_groups(state)
    same = {(a, b) for group in exact for a in group.keys for b in group.keys if a < b}
    signatures: dict[str, frozenset[int]] = {}
    needs_visual, unreadable = [], []
    seen: set[str] = set()
    for item in sorted(state.resources, key=lambda entry: entry.resource.key):
        if item.status != "current" or item.resource.kind not in kinds:
            continue
        if item.sha256 in seen:
            continue
        try:
            record = document_text(root, item.resource.key, state)
        except CampusError:
            unreadable.append(item.resource.key)
            continue
        signature = _sketch(" ".join(page.text for page in record.pages))
        if signature is None:
            needs_visual.append(item.resource.key)
            continue
        seen.add(record.sha256)
        signatures[item.resource.key] = signature
    keys = sorted(signatures)
    pairs = [
        NearPair(left=left, right=right, similarity=round(value, 3))
        for index, left in enumerate(keys)
        for right in keys[index + 1 :]
        if (left, right) not in same
        and (value := _similarity(signatures[left], signatures[right])) >= NEAR_THRESHOLD
    ]
    pairs.sort(key=lambda pair: (-pair.similarity, pair.left, pair.right))
    return DuplicateReport(
        exact=exact,
        near=tuple(pairs),
        needs_visual=tuple(needs_visual),
        unreadable=tuple(unreadable),
    )

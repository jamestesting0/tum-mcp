"""Budgeted evidence checks; support alternatives never become independent votes."""

from dataclasses import dataclass, field
from typing import Literal, assert_never

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_data import stale_lectures
from tum_mcp.lecture_processing.receipts import evidence_bytes
from tum_mcp.study_content import SourceVersion
from tum_mcp.study_knowledge_models import Evidence, LectureEvidence, SourceEvidence, SupportGroup
from tum_mcp.study_knowledge_store import CourseInputs, Observation
from tum_mcp.study_store import confined

EvidenceState = Literal["current", "stale", "unverified", "unknown"]


@dataclass(frozen=True, slots=True)
class Validity:
    state: EvidenceState
    reason: str = ""

    @property
    def current(self) -> bool:
        return self.state == "current"


@dataclass(frozen=True, slots=True)
class GroupStatus:
    key: str
    current: bool
    evidence: tuple[Validity, ...]


@dataclass(slots=True)
class EvidenceChecks:
    """Mutable per-request memo and budget; never stores anything on disk."""

    inputs: CourseInputs
    full: bool = False
    sources: dict[tuple[str, str], Validity] = field(default_factory=dict)
    lectures: dict[str, Validity] = field(default_factory=dict)
    payloads: set[str] = field(default_factory=set)
    exhausted: bool = False

    def source(self, version: SourceVersion) -> Validity:
        identity = (version.key, version.sha256)
        if identity in self.sources:
            return self.sources[identity]
        stored = self.inputs.resources.get(version.key)
        if stored is None:
            result = Validity("unknown", "source is not in the current inventory")
        elif stored.status != "current" or stored.sha256 != version.sha256 or stored.path is None:
            result = Validity("stale", "source state or expected revision is not current")
        elif not self.full and version.key not in self.payloads and len(self.payloads) >= 64:
            self.exhausted = True
            result = Validity("unverified", "source verification budget exhausted")
        else:
            self.payloads.add(version.key)
            path = confined(self.inputs.root, stored.path)
            try:
                actual = self.inputs.reader.fingerprint(path, 50 * 1024**2)
            except OSError:
                result = Validity("unverified", "source payload could not be read")
            except CampusError as error:
                if error.code != Code.INVALID_RESPONSE:
                    raise
                result = Validity("unverified", "source payload is occupied or oversized")
            else:
                self.inputs.reader.record(path, Observation(actual, 50 * 1024**2))
                result = (
                    Validity("current")
                    if actual == version.sha256
                    else Validity("stale", "source bytes are missing or changed")
                )
        self.sources[identity] = result
        return result

    def lecture(self, key: str) -> Validity:
        if key in self.lectures:
            return self.lectures[key]
        content = self.inputs.lectures
        lecture = (
            next((item for item in content.lectures if item.key == key), None) if content else None
        )
        if content is None or lecture is None:
            return Validity("unknown", "lecture is missing")
        new_sources = {s.key for s in lecture.sources} - self.payloads
        if not self.full and (len(self.lectures) >= 4 or len(self.payloads | new_sources) > 64):
            self.exhausted = True
            return Validity("unverified", "lecture verification budget exhausted")
        checks = [self.source(source) for source in lecture.sources]
        failed = next((check for check in checks if not check.current), None)
        if failed is not None:
            self.lectures[key] = failed
            return failed
        selected = content.model_copy(update={"lectures": (lecture,)})
        try:
            stale = stale_lectures(
                self.inputs.root,
                self.inputs.state,
                selected,
                read_observer=self.inputs.reader.observe,
            )
            if not lecture.recording.synthetic:
                evidence_bytes(
                    self.inputs.root,
                    lecture.recording.key,
                    "transcript.json",
                    read_observer=self.inputs.reader.observe,
                )
        except OSError:
            result = Validity("stale", "cached lecture evidence could not be read")
        except CampusError as error:
            if error.code in {Code.SCOPE_DENIED, Code.WORKSPACE_CONFLICT}:
                raise CampusError(
                    error.code, "Cached lecture evidence is outside this course scope."
                ) from None
            result = Validity("stale", f"cached lecture evidence failed {error.code}")
        else:
            result = (
                Validity("stale", "lecture source or receipt is stale")
                if stale
                else Validity("current")
            )
        self.lectures[key] = result
        return result

    def timed(self, reference: LectureEvidence) -> Validity:
        content = self.inputs.lectures
        if content is None:
            return Validity("unknown", "lecture workspace is missing")
        lecture = next((item for item in content.lectures if item.key == reference.lecture), None)
        evidence = next((item for item in content.evidence if item.key == reference.evidence), None)
        if lecture is None or evidence is None:
            return Validity("unknown", "timed evidence reference is missing")
        if evidence.interval is None or not evidence.reviewed or evidence.uncertainty:
            return Validity("stale", "timed evidence is unreviewed or uncertain")
        if not any(evidence.key in section.evidence for section in lecture.sections):
            return Validity("stale", "timed evidence belongs to a different lecture")
        if any(
            span.start_s < evidence.interval.end_s and evidence.interval.start_s < span.end_s
            for span in lecture.coverage.uncertain
        ):
            return Validity("stale", "timed evidence overlaps uncertain coverage")
        return self.lecture(lecture.key)

    def selection(self, key: str, keys: tuple[str, ...] | None = None) -> tuple[Validity, ...]:
        content = self.inputs.lectures
        lecture = (
            next((item for item in content.lectures if item.key == key), None) if content else None
        )
        if lecture is None:
            return (Validity("unknown", "lecture is missing"),)
        selected = (
            keys if keys is not None else tuple({e for s in lecture.sections for e in s.evidence})
        )
        if not selected:
            return (Validity("unknown", "no timed evidence for this lecture item"),)
        return tuple(
            self.timed(LectureEvidence(kind="lecture", lecture=key, evidence=e))
            for e in sorted(selected)
        )

    def evidence(self, reference: Evidence) -> Validity:
        match reference:
            case SourceEvidence():
                return self.source(SourceVersion(key=reference.source, sha256=reference.sha256))
            case LectureEvidence():
                return self.timed(reference)
            case unreachable:
                assert_never(unreachable)

    def group(self, group: SupportGroup) -> GroupStatus:
        checks = tuple(self.evidence(item) for item in group.evidence)
        return GroupStatus(group.key, all(item.current for item in checks), checks)

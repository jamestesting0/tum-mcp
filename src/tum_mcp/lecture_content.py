"""Notes-only lecture documents using the course app's existing safe blocks."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from tum_mcp.lecture_evidence import (
    Evidence,
    Figure,
    Interval,
    LectureCoverage,
    Recording,
    merge_intervals,
)
from tum_mcp.settings import Frozen
from tum_mcp.study_content import Block, SourceVersion, Text
from tum_mcp.study_models import Digest, Key


class LectureSection(Frozen):
    key: Key
    title: Text
    blocks: tuple[Block, ...] = Field(min_length=1, max_length=80)
    evidence: tuple[Key, ...] = Field(min_length=1, max_length=100)
    figures: tuple[Figure, ...] = Field(default=(), max_length=50)


class Lecture(Frozen):
    key: Key
    title: Text
    recording: Recording
    overview: Text
    takeaways: tuple[Text, ...] = Field(min_length=1, max_length=20)
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=100)
    checked_at: Annotated[str, Field(min_length=1, max_length=100)]
    coverage: LectureCoverage
    sections: tuple[LectureSection, ...] = Field(min_length=1, max_length=300)

    @property
    def semantic_revision(self) -> Digest:
        payload = self.model_dump(mode="json", exclude={"checked_at", "coverage", "sources"})
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @model_validator(mode="after")
    def integrity(self) -> "Lecture":
        for collection in (self.sections, self.sources):
            if len({item.key for item in collection}) != len(collection):
                raise ValueError("Lecture section and source keys must be unique.")
        source_ids = {item.key for item in self.sources}
        if any(
            not set(block.sources) <= source_ids
            for section in self.sections
            for block in section.blocks
        ):
            raise ValueError("Lecture block cites an undeclared source.")
        combined = merge_intervals(self.coverage.eligible + self.coverage.excluded)
        if combined != (Interval(start_s=0, end_s=self.recording.duration_s),):
            raise ValueError("Eligible and excluded intervals must partition the actual recording.")
        return self


class LectureContent(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    lectures: tuple[Lecture, ...] = Field(min_length=1, max_length=300)
    evidence: tuple[Evidence, ...] = Field(min_length=1, max_length=30000)

    @model_validator(mode="after")
    def references(self) -> "LectureContent":
        if len({item.key for item in self.lectures}) != len(self.lectures):
            raise ValueError("Lecture keys must be unique.")
        evidence = {item.key: item for item in self.evidence}
        if len(evidence) != len(self.evidence):
            raise ValueError("Evidence keys must be unique.")
        used: set[str] = set()
        for lecture in self.lectures:
            sources = {item.key: item.sha256 for item in lecture.sources}
            for section in lecture.sections:
                selected = set(section.evidence)
                if not selected <= evidence.keys():
                    raise ValueError("Lecture section references unknown evidence.")
                primary = [evidence[key] for key in selected if evidence[key].interval is not None]
                if not primary:
                    raise ValueError(
                        "Each teaching section needs timed primary recording evidence."
                    )
                for key in selected | {figure.evidence for figure in section.figures}:
                    item = evidence.get(key)
                    if item is None or sources.get(item.source_key) != item.source_sha256:
                        raise ValueError("Evidence must match a declared source version.")
                    if item.interval is not None:
                        if item.recording_id != lecture.recording.recording_id or not any(
                            span.start_s
                            <= item.interval.start_s
                            < item.interval.end_s
                            <= span.end_s
                            for span in merge_intervals(lecture.coverage.processed)
                        ):
                            raise ValueError(
                                "Evidence must belong to processed time of this recording."
                            )
                    if lecture.coverage.status == "complete" and (
                        not item.reviewed or item.uncertainty
                    ):
                        raise ValueError(
                            "Complete notes require reviewed, resolved cited evidence."
                        )
                    used.add(key)
                for figure in section.figures:
                    frame = evidence[figure.evidence]
                    if (
                        figure.evidence not in selected
                        or frame.kind != "frame"
                        or frame.interval is None
                        or not frame.interval.start_s
                        <= figure.captured_at_s
                        <= frame.interval.end_s
                    ):
                        raise ValueError(
                            "Figure needs declared frame evidence at its actual capture time."
                        )
        if used != evidence.keys():
            raise ValueError("Remove unused evidence from the authored notes document.")
        return self

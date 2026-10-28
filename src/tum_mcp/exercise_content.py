"""Bounded, source-linked prepared guidance; no evaluators or network services."""

import json
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from tum_mcp.exercise_checks import Check
from tum_mcp.exercise_checks import ChoiceCheck as ChoiceCheck
from tum_mcp.exercise_checks import NumericCheck as NumericCheck
from tum_mcp.exercise_checks import SelfCheck as SelfCheck
from tum_mcp.settings import Frozen
from tum_mcp.study_content import VISUAL_RULE, Block, SourceVersion, Text, has_visual
from tum_mcp.study_models import Key
from tum_mcp.study_store import digest


class GuidanceStep(Frozen):
    key: Key
    purpose: Text
    prompt: Text
    sources: tuple[Key, ...] = Field(default=(), max_length=30)
    blocks: tuple[Block, ...] = Field(default=(), max_length=20)
    check: Check | None = None
    hints: tuple[Text, ...] = Field(default=(), max_length=6)
    explanation: Text


class Prerequisite(Frozen):
    unit: Key
    explanation: Text


class WorkedSolution(Frozen):
    origin: Literal["authored", "official"] = "authored"
    official_source: Key | None = None
    blocks: tuple[Block, ...] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def attribution(self) -> "WorkedSolution":
        if (self.origin == "official") != (self.official_source is not None):
            raise ValueError("Official solutions need their actual official source.")
        return self


class TransferTask(Frozen):
    prompt: Text
    answer: Text


class Exercise(Frozen):
    key: Key
    label: Text
    title: Text
    kind: Literal["original", "distilled"] = "original"
    distilled_from: tuple[Key, ...] = Field(default=(), max_length=10)
    concepts: tuple[Text, ...] = Field(default=(), max_length=12)
    sources: tuple[SourceVersion, ...] = Field(min_length=1, max_length=30)
    statement: tuple[Block, ...] = Field(min_length=1, max_length=40)
    parts: tuple[Text, ...] = Field(default=(), max_length=50)
    objectives: tuple[Text, ...] = Field(min_length=1, max_length=12)
    prerequisites: tuple[Prerequisite, ...] = Field(default=(), max_length=10)
    steps: tuple[GuidanceStep, ...] = Field(min_length=1, max_length=50)
    solution: WorkedSolution
    transfer: TransferTask | None = None

    @model_validator(mode="after")
    def references(self) -> "Exercise":
        distilled = self.kind == "distilled"
        if distilled != bool(self.distilled_from) or self.key in self.distilled_from:
            raise ValueError("Distilled practice names the original exercises it trains.")
        if distilled and not has_visual(self.statement):
            raise ValueError(f"Distilled practice needs {VISUAL_RULE}.")
        source_keys = {item.key for item in self.sources}
        if len(source_keys) != len(self.sources):
            raise ValueError("Exercise source keys must be distinct.")
        if len({step.key for step in self.steps}) != len(self.steps):
            raise ValueError("Exercise step keys must be distinct.")
        for item in (*self.statement, *self.solution.blocks, *self.steps):
            if not set(item.sources) <= source_keys:
                raise ValueError("Exercise content cites an undeclared source.")
        for step in self.steps:
            for block in step.blocks:
                if not set(block.sources) <= source_keys:
                    raise ValueError("Step content cites an undeclared source.")
            if step.check and step.check.kind == "plot":
                if not set(step.check.plot.sources) <= source_keys:
                    raise ValueError("Plot check cites an undeclared source.")
            if step.check and step.check.kind == "graph":
                if not set(step.check.graph.sources) <= source_keys:
                    raise ValueError("Graph check cites an undeclared source.")
        if self.solution.official_source and self.solution.official_source not in source_keys:
            raise ValueError("The official solution source must be declared.")
        return self


class ExerciseSet(Frozen):
    key: Key
    title: Text
    summary: Text | None = None
    category: Text | None = None
    week: Text | None = None
    due_at: AwareDatetime | None = None
    exercises: tuple[Exercise, ...] = Field(min_length=1, max_length=100)


class ExerciseContent(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    sets: tuple[ExerciseSet, ...] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def identities(self) -> "ExerciseContent":
        if len({item.key for item in self.sets}) != len(self.sets):
            raise ValueError("Exercise set keys must be distinct.")
        exercises = [exercise for item in self.sets for exercise in item.exercises]
        if len({item.key for item in exercises}) != len(exercises):
            raise ValueError("Exercise identities must be unique across sets.")
        originals = {item.key for item in exercises if item.kind == "original"}
        if any(not set(item.distilled_from) <= originals for item in exercises):
            raise ValueError("Distilled practice must point to original exercises in this file.")
        versions: dict[str, str] = {}
        for exercise in exercises:
            for source in exercise.sources:
                if source.key in versions and versions[source.key] != source.sha256:
                    raise ValueError("A source cannot have conflicting versions in one workspace.")
                versions[source.key] = source.sha256
        return self


def exercise_revision(exercise: Exercise) -> str:
    """Reviewed provenance or navigation changes do not erase learning attempts."""
    value = exercise.model_dump(mode="json", exclude={"label", "title", "sources"})
    # New optional response controls must not invalidate unchanged legacy attempts.
    for step in value["steps"]:
        if not step.get("blocks"):
            step.pop("blocks", None)
        check = step.get("check")
        if check and check["kind"] == "self_check":
            if check.get("format") == "text":
                check.pop("format", None)
            for field in ("language", "starter_code"):
                if check.get(field) is None:
                    check.pop(field, None)
    value["source_keys"] = sorted(source.key for source in exercise.sources)
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())

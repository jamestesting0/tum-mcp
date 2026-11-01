"""Machine records for prepared Study adaptations, not an audio generation service."""

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import Field, RootModel, field_validator, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_content import SourceVersion
from tum_mcp.study_models import Digest, Key
from tum_mcp.video_content import Locator, Short, Stem, VoiceProfile, canonical, sha256

PositiveSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]
AudioSeconds = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class MediaFile(Frozen):
    path: Annotated[str, Field(min_length=1, max_length=300)]
    sha256: Digest

    @field_validator("path")
    @classmethod
    def relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
            raise ValueError("Use a confined relative POSIX path.")
        if value != path.as_posix() or value == ".":
            raise ValueError("Use a canonical file path.")
        return value


class AudioFile(MediaFile):
    size: int = Field(ge=1, le=8 * 1024**3)


class TeachingReviewFile(MediaFile):
    guidance_sha256: Digest


class AudioUnit(Frozen):
    unit: Key
    semantic_sha256: Digest


class AudioCoverage(Frozen):
    unit: Key
    locator: Locator
    section: Key
    chapter: Key
    mode: Literal["spoken", "study_required", "missing"]
    reason: Annotated[str, Field(min_length=1, max_length=600)] | None = None

    @model_validator(mode="after")
    def disclosed(self) -> "AudioCoverage":
        if self.mode != "spoken" and not self.reason:
            raise ValueError("Non-spoken coverage names the specific dependency or gap.")
        return self


def category_hash(title: str, units: tuple[AudioUnit, ...]) -> str:
    return sha256(canonical({"title": title, "units": [u.model_dump(mode="json") for u in units]}))


class AudioCategory(Frozen):
    key: Key
    stem: Stem
    title: Short
    units: tuple[AudioUnit, ...] = Field(max_length=300)
    category_sha256: Digest
    coverage: tuple[AudioCoverage, ...] = Field(max_length=5000)

    @model_validator(mode="after")
    def consistent(self) -> "AudioCategory":
        units = [item.unit for item in self.units]
        if len(units) != len(set(units)):
            raise ValueError("Category units must be unique and ordered.")
        if any(entry.unit not in units for entry in self.coverage):
            raise ValueError("Coverage may reference only the category's units.")
        if category_hash(self.title, self.units) != self.category_sha256:
            raise ValueError("category_sha256 does not match the title and ordered units.")
        return self


class ChunkInput(Frozen):
    key: Key
    sha256: Digest


class AudioReceipt(AudioCategory):
    units: tuple[AudioUnit, ...] = Field(min_length=1, max_length=300)
    source_references: tuple[SourceVersion, ...] = Field(min_length=1, max_length=300)
    script: AudioFile
    track: AudioFile
    chapters: AudioFile
    voice: VoiceProfile
    chunk_inputs: tuple[ChunkInput, ...] = Field(min_length=1, max_length=5000)
    duration: PositiveSeconds
    teaching_review: TeachingReviewFile
    validation: MediaFile
    coverage: tuple[AudioCoverage, ...] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def chunks(self) -> "AudioReceipt":
        keys = [item.key for item in self.chunk_inputs]
        if len(keys) != len(set(keys)):
            raise ValueError("Chunk input keys must be unique.")
        if {entry.unit for entry in self.coverage} != {unit.unit for unit in self.units}:
            raise ValueError("Coverage must include every requested unit.")
        if not self.teaching_review.path.startswith(
            ".build/"
        ) or not self.validation.path.startswith(".build/"):
            raise ValueError("Audio review and validation evidence stays under audio/.build/.")
        expected = {
            "script": f"scripts/{self.stem}.txt",
            "track": f"tracks/{self.stem}.m4a",
            "chapters": f"chapters/{self.stem}.json",
        }
        for name, path in expected.items():
            if getattr(self, name).path != path:
                raise ValueError(f"{name} must use its category stem beneath audio/.")
        return self


class AudioManifest(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    categories: dict[Key, AudioReceipt] = Field(default_factory=dict, max_length=300)

    @model_validator(mode="after")
    def identities(self) -> "AudioManifest":
        if any(key != item.key for key, item in self.categories.items()):
            raise ValueError("Audio manifest keys must match their receipt keys.")
        stems = [item.stem for item in self.categories.values()]
        if len(stems) != len(set(stems)):
            raise ValueError("Audio category stems must be unique.")
        return self


class PlannedAudio(AudioCategory):
    pending: Literal["new", "changed", "removed", "moved", "missing", "none"]
    voice: VoiceProfile | None = None

    @model_validator(mode="after")
    def active(self) -> "PlannedAudio":
        if not self.units and self.pending != "removed":
            raise ValueError("Active planned categories need at least one unit.")
        if self.pending != "removed" and (
            {entry.unit for entry in self.coverage} != {unit.unit for unit in self.units}
        ):
            raise ValueError("Coverage targets must include every requested unit.")
        return self


class AudioPlan(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    content_sha256: Digest
    category_order: tuple[Key, ...] = Field(max_length=300)
    categories: dict[Key, PlannedAudio] = Field(default_factory=dict, max_length=300)

    @model_validator(mode="after")
    def identities(self) -> "AudioPlan":
        if any(key != item.key for key, item in self.categories.items()):
            raise ValueError("Audio plan keys must match category keys.")
        active = {key for key, item in self.categories.items() if item.pending != "removed"}
        if (
            len(set(self.category_order)) != len(self.category_order)
            or set(self.category_order) != active
        ):
            raise ValueError("category_order lists every active category exactly once.")
        units = [
            unit.unit
            for item in self.categories.values()
            if item.pending != "removed"
            for unit in item.units
        ]
        if len(units) != len(set(units)):
            raise ValueError("A unit has exactly one planned primary category.")
        stems = [item.stem for item in self.categories.values()]
        if len(stems) != len(set(stems)):
            raise ValueError("Audio category stems must be unique.")
        return self


class AudioChapter(Frozen):
    key: Key
    title: Short
    start: AudioSeconds
    end: PositiveSeconds

    @model_validator(mode="after")
    def interval(self) -> "AudioChapter":
        if self.end <= self.start:
            raise ValueError("Chapter end must follow its start.")
        return self


class AudioChapters(RootModel[tuple[AudioChapter, ...]]):
    @model_validator(mode="after")
    def ordered(self) -> "AudioChapters":
        if not self.root or len({c.key for c in self.root}) != len(self.root):
            raise ValueError("Audio chapters must be nonempty with unique keys.")
        if any(b.start < a.end for a, b in zip(self.root, self.root[1:], strict=False)):
            raise ValueError("Audio chapters must be ordered without overlaps.")
        return self


class AudioTool(Frozen):
    name: Annotated[str, Field(min_length=1, max_length=120)]
    version: Annotated[str, Field(min_length=1, max_length=200)]


class AudioValidation(Frozen):
    schema_version: Literal[1] = 1
    artifact_sha256: Digest
    tool: AudioTool
    duration: PositiveSeconds
    codec: str
    container: str
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    decoded: bool
    loudness_lufs: float = Field(allow_inf_nan=False)
    true_peak_dbtp: float = Field(allow_inf_nan=False)
    probe: MediaFile
    decode: MediaFile
    loudness: MediaFile

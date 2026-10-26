"""Validated, course-bound local inventories. No network or credential access."""

from pathlib import PurePosixPath
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import Field, field_validator, model_validator

from tum_mcp.settings import Frozen

Key = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_.-]{0,99}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ProviderName = Literal["moodle", "artemis", "zulip", "sample", "tum_live", "studocu"]
Kind = Literal["exam", "content", "exercise", "other"]
FOLDERS = {"exam": "exams", "content": "content", "exercise": "exercises", "other": "other"}


class Binding(Frozen):
    key: Key
    provider: ProviderName
    course_id: Annotated[str, Field(min_length=1, max_length=100)]
    account_id: str | None = Field(default=None, max_length=100)
    course_slug: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{1,100}$", exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def live_identity(self) -> "Binding":
        if self.provider == "tum_live" and (
            not self.course_id.isdecimal() or int(self.course_id) <= 0 or not self.course_slug
        ):
            raise ValueError("TUM-Live bindings need separate numeric course ID and opaque slug.")
        if self.provider != "tum_live" and self.course_slug is not None:
            raise ValueError("Only TUM-Live bindings use a course slug.")
        return self


class Course(Frozen):
    key: Key
    title: Annotated[str, Field(min_length=1, max_length=200)]
    semester: Annotated[str, Field(min_length=1, max_length=100)]
    synthetic: bool = False
    bindings: tuple[Binding, ...] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def distinct_bindings(self) -> "Course":
        keys = [item.key for item in self.bindings]
        if len(set(keys)) != len(keys):
            raise ValueError("Course bindings must have unique keys.")
        sample = [item.provider == "sample" for item in self.bindings]
        if (any(sample) and not all(sample)) or self.synthetic != all(sample):
            raise ValueError(
                "Synthetic courses use sample bindings only; real courses use real providers."
            )
        if not self.title.strip() or not self.semester.strip():
            raise ValueError("Course title and semester are required.")
        return self


class Coverage(Frozen):
    binding: Key
    status: Literal["complete", "partial", "unavailable"]
    checked_at: Annotated[str, Field(min_length=1, max_length=100)]
    note: str = Field(default="", max_length=2000)


class StudocuProvenance(Frozen):
    document_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    course_id: Annotated[str, Field(pattern=r"^[1-9][0-9]{0,19}$")]
    storage_group: Literal["summaries", "exams", "other"]
    raw_category: str = Field(default="", max_length=200)
    document_type: Literal["exam", "mock", "solution", "summary", "other"] = "other"
    year: int | None = Field(default=None, ge=1900, le=2100)
    lecturer: str | None = Field(default=None, max_length=200)
    language: str | None = Field(default=None, max_length=50)
    acquisition_method: Literal["browser_import"] = "browser_import"
    acquired_at: str | None = Field(default=None, max_length=100)
    file_sha256: Digest | None = None
    page_count: int | None = Field(default=None, ge=1, le=1500)


class Resource(Frozen):
    key: Key
    binding: Key
    kind: Kind
    title: Annotated[str, Field(min_length=1, max_length=300)]
    url: Annotated[str, Field(max_length=4000)]
    locator: str = Field(default="", max_length=500)
    revision: str | None = Field(default=None, max_length=200)
    text: str | None = Field(default=None, max_length=2_000_000)
    source_file: str | None = Field(default=None, max_length=500)
    studocu: StudocuProvenance | None = Field(default=None, exclude_if=lambda value: value is None)

    @field_validator("url")
    @classmethod
    def public_link(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("Use a source link without embedded credentials.")
        if any(
            any(
                secret in key.casefold()
                for secret in ("token", "secret", "password", "sesskey", "api_key", "apikey", "jwt")
            )
            for key, _ in parse_qsl(parsed.query)
        ):
            raise ValueError("Source links must not contain authentication parameters.")
        return value

    @field_validator("source_file")
    @classmethod
    def relative_file(cls, value: str | None) -> str | None:
        if value is not None:
            path = PurePosixPath(value)
            if path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
                raise ValueError("Import files must be relative to the snapshot directory.")
        return value

    @model_validator(mode="after")
    def one_payload(self) -> "Resource":
        if self.text is not None and self.source_file is not None:
            raise ValueError("Supply text or a file, not both.")
        return self


class Snapshot(Frozen):
    schema_version: Literal[1, 2] = 1
    course: Course
    coverage: tuple[Coverage, ...] = Field(max_length=30)
    resources: tuple[Resource, ...] = Field(max_length=10000)
    retained_bindings: tuple[Key, ...] = Field(default=(), exclude_if=lambda value: not value)

    @model_validator(mode="after")
    def scope(self) -> "Snapshot":
        if self.schema_version < 2 and any(
            item.provider == "tum_live" for item in self.course.bindings
        ):
            raise ValueError("TUM-Live sources require schema version 2; do not downgrade them.")
        bindings = {item.key for item in self.course.bindings}
        keys = [item.key for item in self.resources]
        coverage = [item.binding for item in self.coverage]
        if len(keys) != len(set(keys)) or len(coverage) != len(set(coverage)):
            raise ValueError("Resource and coverage keys must be unique.")
        retained = set(self.retained_bindings)
        if len(retained) != len(self.retained_bindings) or not retained <= bindings:
            raise ValueError("Retained bindings must be unique course bindings.")
        if set(coverage) != bindings - retained or any(
            r.binding not in bindings - retained for r in self.resources
        ):
            raise ValueError("Every course binding needs explicit coverage and scoped resources.")
        validate_provenance(self.course, self.resources)
        return self


def is_studocu_link(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").rstrip(".")
    return hostname == "studocu.com" or hostname.endswith(".studocu.com")


def validate_provenance(course: Course, resources: tuple[Resource, ...]) -> None:
    bindings = {item.key: item for item in course.bindings}
    for resource in resources:
        binding = bindings.get(resource.binding)
        if binding is None:
            raise ValueError("Resource is not bound to this course.")
        source = resource.studocu
        if binding.provider != "studocu":
            if source is not None:
                raise ValueError("Studocu sources require a Studocu binding and provenance.")
            continue
        if source is None or source.course_id != binding.course_id:
            raise ValueError("Studocu resources require course-matched provenance.")
        parsed = urlsplit(resource.url)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"www.studocu.com", "studocu.com"}
            or parsed.port not in {None, 443}
            or parsed.query
            or parsed.fragment
            or "document" not in parts
            or parts[-1] != source.document_id
            or resource.key != f"studocu-{source.document_id}"
        ):
            raise ValueError("Studocu document identity or canonical link is invalid.")


def material_path(resource: Resource, suffix: str) -> str:
    if resource.studocu is not None:
        return f"materials/studocu/{resource.studocu.storage_group}/material-{resource.key}{suffix}"
    return f"materials/{FOLDERS[resource.kind]}/material-{resource.key}{suffix}"


class ResourceState(Frozen):
    resource: Resource
    path: str | None = None
    alias_of: str | None = None
    sha256: Digest | None = None
    status: Literal["current", "needs_fetch", "local_edit", "withdrawn"]

    @model_validator(mode="after")
    def material_path(self) -> "ResourceState":
        if self.alias_of is not None and (self.path is not None or self.resource.studocu is None):
            raise ValueError("Only Studocu material can be an alias without its own path.")
        if self.status == "current" and (
            (self.path is None and self.alias_of is None) or self.sha256 is None
        ):
            raise ValueError("Current material requires a stored path and hash.")
        if self.path is not None:
            path = PurePosixPath(self.path)
            valid = (
                path.as_posix() == material_path(self.resource, path.suffix)
                if self.resource.studocu is not None
                else len(path.parts) == 3
                and path.parts[:2] == ("materials", FOLDERS[self.resource.kind])
                and path.name.startswith(f"material-{self.resource.key}.")
            )
            if not valid or "\\" in self.path or ":" in self.path:
                raise ValueError("Stored material path does not match its resource.")
        if self.status == "current" and self.resource.studocu is not None:
            source = self.resource.studocu
            if (
                source.file_sha256 != self.sha256
                or source.page_count is None
                or source.acquired_at is None
                or (self.path is not None and not self.path.endswith(".pdf"))
            ):
                raise ValueError("Current Studocu material requires a validated PDF receipt.")
        return self


class StudyState(Frozen):
    schema_version: Literal[1, 2] = 1
    course: Course
    coverage: tuple[Coverage, ...]
    resources: tuple[ResourceState, ...]
    generation: Digest
    agents_block_sha256: Digest

    @model_validator(mode="after")
    def provider_version(self) -> "StudyState":
        if self.schema_version < 2 and any(
            item.provider == "tum_live" for item in self.course.bindings
        ):
            raise ValueError("TUM-Live state requires schema version 2; do not downgrade it.")
        return self

    @model_validator(mode="after")
    def scope(self) -> "StudyState":
        bindings = {binding.key for binding in self.course.bindings}
        coverage = [item.binding for item in self.coverage]
        keys = [item.resource.key for item in self.resources]
        if set(coverage) != bindings or len(coverage) != len(set(coverage)):
            raise ValueError("Stored coverage must include every binding exactly once.")
        if len(keys) != len(set(keys)):
            raise ValueError("Stored resource keys must be unique.")
        validate_provenance(self.course, tuple(item.resource for item in self.resources))
        resources = {item.resource.key: item for item in self.resources}
        for item in self.resources:
            if item.alias_of is None:
                continue
            target = resources.get(item.alias_of)
            source = item.resource.studocu
            other = target.resource.studocu if target else None
            if (
                target is None
                or target.alias_of is not None
                or target.path is None
                or source is None
                or other is None
                or source.year is None
                or item.sha256 != target.sha256
                or source.page_count != other.page_count
                or item.resource.binding != target.resource.binding
                or (source.course_id, source.storage_group, source.document_type, source.year)
                != (other.course_id, other.storage_group, other.document_type, other.year)
            ):
                raise ValueError("Studocu alias target is invalid or incompatible.")
        return self


def resolved_material_path(state: StudyState, item: ResourceState) -> str | None:
    """Resolve a validated one-hop alias without changing its source identity."""
    if item.alias_of is None:
        return item.path
    return next(source.path for source in state.resources if source.resource.key == item.alias_of)

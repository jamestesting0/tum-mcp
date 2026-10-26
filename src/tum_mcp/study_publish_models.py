"""Course-bound publishing settings and credential-free deployment receipts."""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Final, Literal
from urllib.parse import urlsplit

from pydantic import Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen
from tum_mcp.study_models import Course, Digest
from tum_mcp.study_store import (
    Write,
    apply,
    digest,
    load_state,
    private_name,
    private_path,
    read_bytes,
)

CONFIG: Final = "github.json"
SETUP: Final = "github-setup.json"
GitSha = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$")]
RepositoryName = Annotated[
    str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
]


class PublicationSetup(Frozen):
    course_identity: Digest
    repository: RepositoryName
    public_site: Literal[True]
    include_exercises: bool = Field(default=False, strict=True)


class Publication(PublicationSetup):
    schema_version: Literal[1] = 1
    branch: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9_./-]+$")
    auto_sync: bool = True
    commit: GitSha
    site_digest: Digest | None = None
    deployed_commit: GitSha | None = None
    hosted_url: str | None = None

    @field_validator("hosted_url")
    @classmethod
    def safe_url(cls, value: str | None) -> str | None:
        if value is not None:
            parts = urlsplit(value)
            if (
                parts.scheme != "https"
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
                or parts.query
                or parts.fragment
            ):
                raise PydanticCustomError(
                    "publication_url", "Use a credential-free HTTPS site URL."
                )
        return value


@dataclass(frozen=True, slots=True)
class PublishReport:
    status: Literal["deployed", "unchanged", "pending", "failed", "paused"]
    repository: str
    hosted_url: str | None = None
    commit: str | None = None
    message: str = ""


def course_identity(course: Course) -> str:
    return digest(f"{course.key}\n{course.semester}".encode())


def repository_name(course: Course) -> str:
    """Choose a stable, lowercase GitHub project name, including its semester."""

    def slug(value: str) -> str:
        label = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
        return re.sub(r"[^a-z0-9]+", "-", label).strip("-")

    semester = (slug(course.semester) or "term-" + course_identity(course)[:8])[:32].rstrip("-")
    title = slug(course.title) or course.key
    return f"study-{title[: 93 - len(semester)].rstrip('-')}-{semester}"


def load_publication(root: Path) -> Publication | None:
    path = private_path(root, CONFIG)
    raw = read_bytes(path)
    if raw is None:
        return None
    try:
        if len(raw) > 16384:
            raise CampusError(Code.INVALID_RESPONSE, "Publishing settings exceed 16 KiB.")
        result = Publication.model_validate_json(raw)
    except ValidationError:
        raise CampusError(Code.INVALID_RESPONSE, "Publishing settings need local review.") from None
    if result.course_identity != course_identity(load_state(root).course):
        raise CampusError(Code.SCOPE_DENIED, "Publishing settings belong to another course.")
    return result


def save_publication(root: Path, publication: Publication) -> None:
    path = private_path(root, CONFIG)
    apply(
        root,
        (
            Write(
                private_name(root, CONFIG),
                read_bytes(path),
                publication.model_dump_json(indent=2).encode(),
            ),
        ),
    )


def load_setup(root: Path) -> PublicationSetup | None:
    """Recover the chosen name after an interrupted repository-creation request."""
    raw = read_bytes(private_path(root, SETUP))
    if raw is None:
        return None
    try:
        setup = PublicationSetup.model_validate_json(raw)
    except ValidationError:
        raise CampusError(
            Code.INVALID_RESPONSE, "Interrupted GitHub setup needs local review."
        ) from None
    if setup.course_identity != course_identity(load_state(root).course):
        raise CampusError(
            Code.SCOPE_DENIED, "Interrupted publishing setup belongs to another course."
        )
    return setup

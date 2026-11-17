"""Bounded GitHub API calls through host-owned gh authentication; never extract tokens."""

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Literal, NoReturn

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError, field_validator

from tum_mcp.course.app.publish_models import GitSha, Publication, RepositoryName
from tum_mcp.errors import CampusError, Code


class Response(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Account(Response):
    login: str


class Repository(Response):
    full_name: RepositoryName
    private: bool
    default_branch: str
    size: int = 0  # KiB, as GitHub reports it


class GitObject(Response):
    sha: GitSha


class Commit(GitObject):
    tree: GitObject


class Entry(GitObject):
    path: str
    mode: str
    type: str


class Tree(GitObject):
    tree: tuple[Entry, ...]
    truncated: bool = False


class Head(Response):
    object: GitObject


class Pages(Response):
    html_url: str
    public: bool
    source: dict[str, str]
    build_type: str = "legacy"

    @field_validator("html_url")
    @classmethod
    def safe_url(cls, value: str) -> str:
        Publication.safe_url(value)
        return value


class PagesBuild(Response):
    status: str
    commit: str = ""


class Check(Response):
    status: str
    conclusion: str | None = None


class Checks(Response):
    total_count: int
    check_runs: tuple[Check, ...]


class WorkflowRuns(Response):
    total_count: int
    workflow_runs: tuple[Check, ...]


class Status(Response):
    state: str
    total_count: int


class PagesPlanRequired(CampusError):
    """GitHub refused Pages because the account plan excludes private repositories."""


STATUS = re.compile(rb"HTTP (\d{3})")


@dataclass(frozen=True, slots=True)
class GitHub:
    executable: str

    @classmethod
    def discover(cls) -> "GitHub":
        executable = shutil.which("gh")
        if executable is None:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Install GitHub CLI and run gh auth login --hostname github.com.",
            )
        return cls(executable)

    def api[T: BaseModel](
        self,
        endpoint: str,
        model: type[T],
        *,
        method: Literal["GET", "POST", "PATCH"] = "GET",
        payload: JsonValue = None,
        missing_ok: bool = False,
        timeout: int = 45,
    ) -> T | None:
        """Only call github.com; JSON bodies go through stdin and errors omit raw output."""
        result = self._run(endpoint, method, payload, timeout)
        if result.returncode:
            status = STATUS.search(result.stderr)
            code = int(status[1]) if status else None
            if code == 404 and missing_ok:
                return None
            self._fail(endpoint, method, code, result.stderr)
        try:
            return model.model_validate_json(result.stdout)
        except ValidationError:
            raise CampusError(
                Code.INVALID_RESPONSE, "GitHub returned an unexpected response."
            ) from None

    def exists(self, endpoint: str) -> bool:
        """A HEAD request: gh prints a bare `HTTP 404` for a missing object."""
        result = self._run(endpoint, "HEAD", None, 45)
        if not result.returncode:
            return True
        status = STATUS.search(result.stderr)
        code = int(status[1]) if status else None
        if code == 404:
            return False
        self._fail(endpoint, "HEAD", code, result.stderr)

    def _run(
        self, endpoint: str, method: str, payload: JsonValue, timeout: int
    ) -> subprocess.CompletedProcess[bytes]:
        if not endpoint.startswith(("repos/", "user", "orgs/")):
            raise CampusError(Code.SCOPE_DENIED, "Unexpected GitHub API destination.")
        arguments = [
            self.executable,
            "api",
            "--hostname",
            "github.com",
            "--method",
            method,
            "--header",
            "Accept: application/vnd.github+json",
            endpoint,
        ]
        if payload is not None:
            arguments.extend(("--input", "-"))
        environment = dict(os.environ)
        # gh debug logging can echo authenticated requests and study content.
        environment.pop("GH_DEBUG", None)
        environment.update(GH_PROMPT_DISABLED="1", GH_PAGER="cat", NO_COLOR="1")
        try:
            return subprocess.run(  # noqa: S603
                arguments,
                input=json.dumps(payload).encode() if payload is not None else None,
                capture_output=True,
                timeout=timeout,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError):
            raise CampusError(
                Code.OFFLINE, "GitHub could not be reached; local work is preserved."
            ) from None

    @staticmethod
    def _fail(endpoint: str, method: str, code: int | None, stderr: bytes) -> NoReturn:
        """Classify a failure from its status alone; raw CLI output never reaches the message."""
        if code in {401, 403} or (code is None and endpoint == "user"):
            raise CampusError(
                Code.AUTH_REQUIRED,
                "Check gh auth login --hostname github.com and repository/Pages permissions.",
            )
        if code == 422 and endpoint.endswith("/pages") and b"plan does not support" in stderr:
            raise PagesPlanRequired(
                Code.ACTION_REQUIRED,
                "This GitHub plan does not serve Pages from private repositories.",
            )
        raise CampusError(
            Code.ACTION_REQUIRED,
            f"GitHub rejected {method} {endpoint.split('?')[0]}"
            + (f" (HTTP {code})" if code else "")
            + ". Check authentication, repository permissions and Pages plan eligibility.",
        )

    def require[T: BaseModel](
        self,
        endpoint: str,
        model: type[T],
        *,
        method: Literal["GET", "POST", "PATCH"] = "GET",
        payload: JsonValue = None,
        timeout: int = 45,
    ) -> T:
        result = self.api(endpoint, model, method=method, payload=payload, timeout=timeout)
        if result is None:
            raise CampusError(Code.INVALID_RESPONSE, "GitHub omitted a required response.")
        return result

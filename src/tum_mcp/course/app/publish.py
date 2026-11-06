"""Explicit first publication, then incremental publishing after configured study builds."""

import time
from pathlib import Path
from urllib.parse import quote

from filelock import FileLock

from tum_mcp.course.app.github import Account, GitHub, Head, Pages, Repository
from tum_mcp.course.app.publish_checks import create_pages, deployed, verify_pages
from tum_mcp.course.app.publish_models import (
    SETUP,
    Publication,
    PublicationSetup,
    PublishReport,
    RepositoryName,
    course_identity,
    load_publication,
    load_setup,
    repository_name,
    save_publication,
)
from tum_mcp.course.app.publish_site import commit_site, export_site, site_digest
from tum_mcp.course.project.store import (
    Write,
    apply,
    load_state,
    private_name,
    private_path,
    read_bytes,
)
from tum_mcp.errors import CampusError, Code


def configure(
    root: Path,
    *,
    repository: str | None = None,
    site: dict[str, bytes] | None = None,
) -> Publication:
    """Create a private repository only after the caller explicitly requests a public site."""
    from pydantic import TypeAdapter, ValidationError

    root = root.expanduser().resolve()
    with FileLock(str(private_path(root, "publish.lock")), is_singleton=True):
        previous = load_publication(root)
        if previous is not None:
            if repository is not None and repository.casefold() != previous.repository.casefold():
                raise CampusError(
                    Code.WORKSPACE_CONFLICT, "This course already has a publishing repository."
                )
            if previous.schema_version != 2:
                previous = previous.model_copy(update={"schema_version": 2})
                save_publication(root, previous)
            return previous
        interrupted = load_setup(root)
        if (
            interrupted is not None
            and repository is not None
            and interrupted.repository.casefold() != repository.casefold()
        ):
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "Resume the interrupted repository setup before choosing another name.",
            )
        with FileLock(str(private_path(root, "update.lock"))):
            course = load_state(root).course
            if site is None:
                site = export_site(root)
        github = GitHub.discover()
        account = github.require("user", Account)
        chosen = (
            interrupted.repository
            if interrupted
            else repository or f"{account.login}/{repository_name(course)}"
        )
        try:
            chosen = TypeAdapter(RepositoryName).validate_python(chosen)
        except ValidationError:
            raise CampusError(
                Code.ACTION_REQUIRED, "Use a GitHub repository in OWNER/NAME form."
            ) from None
        remote = github.api(f"repos/{chosen}", Repository, missing_ok=True)
        if remote is not None and repository is None and interrupted is None:
            owner, name = chosen.split("/")
            chosen = f"{owner}/{name[:91].rstrip('-')}-{course_identity(course)[:8]}"
            remote = github.api(f"repos/{chosen}", Repository, missing_ok=True)
            if remote is not None:
                raise CampusError(
                    Code.WORKSPACE_CONFLICT,
                    "The generated repository name is occupied; choose --repository OWNER/NAME.",
                )
        if remote is None:
            owner, name = chosen.split("/")
            setup_path = private_path(root, SETUP)
            setup = PublicationSetup(
                course_identity=course_identity(course),
                repository=chosen,
                public_site=True,
            )
            apply(
                root,
                (
                    Write(
                        private_name(root, SETUP),
                        read_bytes(setup_path),
                        setup.model_dump_json().encode(),
                    ),
                ),
            )
            endpoint = (
                "user/repos"
                if owner.casefold() == account.login.casefold()
                else f"orgs/{owner}/repos"
            )
            remote = github.require(
                endpoint,
                Repository,
                method="POST",
                payload={
                    "name": name,
                    "private": True,
                    "auto_init": True,
                    "description": "Generated course study website",
                },
            )
        if not remote.private or remote.full_name.casefold() != chosen.casefold():
            raise CampusError(
                Code.SCOPE_DENIED, "Publishing requires the chosen private repository."
            )
        head = github.require(
            f"repos/{remote.full_name}/git/ref/heads/{quote(remote.default_branch, safe='')}", Head
        )
        publication = Publication(
            schema_version=2,
            course_identity=course_identity(course),
            repository=remote.full_name,
            branch=remote.default_branch,
            commit=head.object.sha,
            public_site=True,
        )
        # Save before uploading: an interrupted setup retries the same repository.
        save_publication(root, publication)
        private_path(root, SETUP).unlink(missing_ok=True)
        return publication


def publish(
    root: Path,
    *,
    wait_seconds: int = 60,
    rebuild: bool = True,
    verify_unchanged: bool = False,
    site: dict[str, bytes] | None = None,
) -> PublishReport:
    """Upload changed site assets and verify deployment for the exact resulting commit."""
    root = root.expanduser().resolve()
    with FileLock(str(private_path(root, "publish.lock")), is_singleton=True):
        publication = load_publication(root)
        if publication is None:
            raise CampusError(
                Code.ACTION_REQUIRED, "Configure study publish with --public-site first."
            )
        if publication.schema_version != 2:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "The saved selective publication needs explicit --public-site consent "
                "for all prepared workspaces.",
            )
        if site is None:
            if rebuild:
                site = build_for_publication(root)
            else:
                with FileLock(str(private_path(root, "update.lock"))):
                    site = export_site(root)
        fingerprint = site_digest(site)
        if (
            fingerprint == publication.site_digest
            and publication.deployed_commit == publication.commit
            and not verify_unchanged
        ):
            return PublishReport(
                "unchanged", publication.repository, publication.hosted_url, publication.commit
            )
        github = GitHub.discover()
        remote = github.require(f"repos/{publication.repository}", Repository)
        if not remote.private or remote.default_branch != publication.branch:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                "The repository visibility or default branch changed; review before publishing.",
            )
        # Check an existing site's source before changing its publishing branch.
        existing = github.api(f"repos/{publication.repository}/pages", Pages, missing_ok=True)
        if existing is not None:
            verify_pages(existing, publication)
        commit = commit_site(github, publication, site)
        publication = publication.model_copy(update={"commit": commit, "site_digest": fingerprint})
        save_publication(root, publication)
        pages = existing or create_pages(github, publication)
        # Validate even server-provided URLs before persisting or printing them.
        publication = Publication.model_validate(
            {**publication.model_dump(), "hosted_url": pages.html_url}
        )
        save_publication(root, publication)
        deadline = time.monotonic() + max(0, min(wait_seconds, 60))
        while not deployed(github, publication):
            if time.monotonic() >= deadline:
                return PublishReport(
                    "pending",
                    publication.repository,
                    publication.hosted_url,
                    commit,
                    "Retry study publish sync; deployment or commit checks are pending.",
                )
            time.sleep(min(3, max(0, deadline - time.monotonic())))
        publication = publication.model_copy(update={"deployed_commit": commit})
        save_publication(root, publication)
        return PublishReport("deployed", publication.repository, publication.hosted_url, commit)


def build_for_publication(root: Path) -> dict[str, bytes]:
    """Build once, then capture one validated public export before network access."""
    from tum_mcp.course.app.build import build

    build(root, publish=False)
    with FileLock(str(private_path(root, "update.lock"))):
        return export_site(root)


def after_build(root: Path) -> PublishReport | None:
    """Keep a valid local build usable if configured publishing is pending or unavailable."""
    try:
        publication = load_publication(root)
        if publication is None:
            return None
        if not publication.auto_sync:
            return PublishReport(
                "paused", publication.repository, publication.hosted_url, publication.commit
            )
        return publish(root, rebuild=False)
    except CampusError as error:
        return PublishReport("failed", "", message=str(error))

import json
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Literal, assert_never

import pytest
from study_publish_fixture import GitHubFixture
from typer.testing import CliRunner

from tum_mcp import study_github, study_preview
from tum_mcp.cli import app
from tum_mcp.errors import CampusError, Code
from tum_mcp.study_build import build
from tum_mcp.study_publish_models import load_publication
from tum_mcp.study_publish_site import MARKER, SITE_FILES


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> GitHubFixture:
    fixture = GitHubFixture()
    monkeypatch.setattr(study_github.shutil, "which", lambda name: "/synthetic/gh")
    monkeypatch.setattr(study_github.subprocess, "run", fixture.run)
    monkeypatch.setenv("GH_DEBUG", "api")
    return fixture


def first_publish(project: Path):
    return CliRunner().invoke(
        app, ["study", "publish", "--project", str(project), "--public-site", "--wait-seconds", "0"]
    )


def change_lesson(project: Path) -> None:
    path = project / "study/content.json"
    content = json.loads(path.read_bytes())
    content["introduction"] += " Updated synthetic lesson."
    path.write_text(json.dumps(content), encoding="utf-8")


def test_proposal_has_no_uploads_or_authentication(project: Path, github: GitHubFixture) -> None:
    # Given a local study website without publication consent.
    # When the agent asks for the publication proposal.
    result = CliRunner().invoke(app, ["study", "publish", "--project", str(project)])
    # Then it shows the privacy boundary without contacting GitHub or creating settings.
    assert result.exit_code == 0, result.output
    proposal = json.loads(result.output)
    assert proposal["repository_visibility"] == "private"
    assert proposal["website_visibility"] == "public"
    assert proposal["suggested_name"].startswith("study-algorithms-graphs-")
    assert github.requests == [] and not (project / ".tum-mcp/github.json").exists()


def test_exercise_scope_is_explicit_and_keeps_the_existing_repository(
    exercise_project: Path, github: GitHubFixture
) -> None:
    root = exercise_project
    assert first_publish(root).exit_code == 0
    before = load_publication(root)
    assert before.include_exercises is False
    saved = root / ".tum-mcp/github.json"
    old = json.loads(saved.read_bytes())
    old.pop("include_exercises")
    saved.write_text(json.dumps(old))
    assert load_publication(root).include_exercises is False
    arguments = ["study", "publish", "--project", str(root), "--wait-seconds", "0"]
    included = CliRunner().invoke(app, [*arguments, "--include-exercises"])
    assert included.exit_code == 0, included.output
    after = load_publication(root)
    assert after.include_exercises is True
    assert (after.repository, after.branch, after.hosted_url) == (
        before.repository,
        before.branch,
        before.hosted_url,
    )
    assert b"sample-relaxation" in github.files(after.repository)["data.mjs"]
    excluded = CliRunner().invoke(app, [*arguments, "--exclude-exercises"])
    assert excluded.exit_code == 0, excluded.output
    assert b"sample-relaxation" not in github.files(after.repository)["data.mjs"]
    assert len(github.repositories) == 1


def test_first_publication_exports_only_the_site(project: Path, github: GitHubFixture) -> None:
    # Given private source, comment and arbitrary files alongside the generated app.
    (project / "study/private.txt").write_text("synthetic-private-original", encoding="utf-8")
    (project / ".tum-mcp/comments.json").write_text("synthetic-local-comment", encoding="utf-8")
    (project / ".env").write_text("synthetic-credential-file", encoding="utf-8")
    # When public site publication is explicitly authorized.
    result = first_publish(project)
    # Then the private repository contains only the site and its ownership marker.
    assert result.exit_code == 0, result.output
    receipt = json.loads(result.output)
    files = github.files(receipt["repository"])
    assert set(files) == {*SITE_FILES, MARKER, "README.md"}
    assert all(b"synthetic-private-original" not in value for value in files.values())
    assert b"data.hosted = true" in files["data.mjs"]
    assert b"data.hosted" not in (project / "study/data.mjs").read_bytes()
    creation = next(request for request in github.requests if request.endpoint == "user/repos")
    assert creation.body["private"] is True
    saved = load_publication(project)
    assert saved.commit == saved.deployed_commit == receipt["commit"]
    assert saved.hosted_url == receipt["hosted_url"]


def test_build_updates_the_same_repository_and_unchanged_build_is_local(
    project: Path,
    github: GitHubFixture,
) -> None:
    # Given a verified publication and an edited local lesson.
    assert first_publish(project).exit_code == 0
    before = load_publication(project)
    change_lesson(project)
    # When the normal build command runs.
    result = CliRunner().invoke(app, ["study", "build", str(project)])
    # Then the same repository and URL advance once, and a repeat requires no API calls.
    assert result.exit_code == 0, result.output
    after = load_publication(project)
    assert after.repository == before.repository and after.hosted_url == before.hosted_url
    assert after.commit != before.commit and after.commit == after.deployed_commit
    assert len(github.repositories) == 1
    count = len(github.requests)
    repeated = build(project)
    assert repeated.publication.status == "unchanged" and len(github.requests) == count


@pytest.mark.parametrize("pending", ["build", "old_commit", "checks", "workflow"])
def test_pending_deployment_retries_without_duplicate_commits(
    project: Path,
    github: GitHubFixture,
    pending: Literal["build", "old_commit", "checks", "workflow"],
) -> None:
    # Given a build or check that has not completed for the uploaded commit.
    match pending:
        case "build":
            github.build_status = "building"
        case "old_commit":
            github.build_commit = "0" * 40
        case "checks":
            github.check_status = "in_progress"
        case "workflow":
            github.workflow_status = "queued"
        case unreachable:
            assert_never(unreachable)
    # When the first publication uploads its site.
    result = first_publish(project)
    # Then it remains explicitly pending and a later retry verifies the same commit.
    assert result.exit_code == 2, result.output
    assert json.loads(result.output)["status"] == "pending"
    pending_publication = load_publication(project)
    assert pending_publication.deployed_commit is None
    commits = len(github.commits)
    github.build_status, github.build_commit, github.check_status = "built", None, "completed"
    github.workflow_status = "completed"
    retry = CliRunner().invoke(
        app, ["study", "publish", "sync", str(project), "--wait-seconds", "0"]
    )
    assert retry.exit_code == 0, retry.output
    assert len(github.commits) == commits
    assert load_publication(project).deployed_commit == pending_publication.commit


def test_plan_failure_retains_a_resumable_private_repository(
    project: Path,
    github: GitHubFixture,
) -> None:
    # Given an account without Pages eligibility for private repositories.
    github.plan_eligible = False
    # When publication reaches the Pages configuration boundary.
    result = first_publish(project)
    # Then it preserves the private repository and retries it after eligibility is fixed.
    assert isinstance(result.exception, CampusError)
    assert "synthetic-private-value" not in str(result.exception)
    assert len(github.repositories) == 1 and all(
        repo["private"] for repo in github.repositories.values()
    )
    github.plan_eligible = True
    retry = first_publish(project)
    assert retry.exit_code == 0, retry.output
    assert len(github.repositories) == 1


def test_lost_creation_response_reuses_the_chosen_repository(
    project: Path,
    github: GitHubFixture,
) -> None:
    # Given a successful GitHub creation whose response never reaches the client.
    github.lose_creation_response = True
    # When setup is interrupted, then retried with the same publication request.
    first = first_publish(project)
    retry = first_publish(project)
    # Then the saved creation intent prevents another repository being created.
    assert isinstance(first.exception, CampusError) and first.exception.code == Code.OFFLINE
    assert retry.exit_code == 0, retry.output
    assert len(github.repositories) == 1
    assert not (project / ".tum-mcp/github-setup.json").exists()


def test_remote_edits_are_not_overwritten(project: Path, github: GitHubFixture) -> None:
    # Given a manually edited generated file and a new local lesson.
    assert first_publish(project).exit_code == 0
    repository = load_publication(project).repository
    github.edit(repository, "styles.css", b"Manual remote changes")
    change_lesson(project)
    # When automatic publication runs after the local build.
    result = build(project)
    # Then it keeps both local work and the remote edit for review.
    assert result.publication.status == "failed"
    assert result.publication.message.startswith("WORKSPACE_CONFLICT")
    assert github.files(repository)["styles.css"] == b"Manual remote changes"
    assert b"Updated synthetic lesson" in (project / "study/data.mjs").read_bytes()


def test_explicit_sync_rechecks_an_unchanged_site(project: Path, github: GitHubFixture) -> None:
    # Given a verified site whose Pages configuration was removed externally.
    assert first_publish(project).exit_code == 0
    repository = load_publication(project).repository
    del github.pages[repository]
    commits = len(github.commits)
    # When the user explicitly requests publication recovery.
    result = CliRunner().invoke(app, ["study", "publish", "sync", str(project)])
    # Then Pages is restored and verified without another content commit.
    assert result.exit_code == 0, result.output
    assert repository in github.pages and len(github.commits) == commits


def test_concurrent_remote_commit_is_rejected(project: Path, github: GitHubFixture) -> None:
    # Given a publication and a competing commit during the next upload.
    assert first_publish(project).exit_code == 0
    repository = load_publication(project).repository
    github.concurrent_push = True
    change_lesson(project)
    # When the generated commit attempts to advance the remote branch.
    result = build(project)
    # Then optimistic publishing preserves the competing change and reports failure.
    assert result.publication.status == "failed"
    assert github.files(repository)["README.md"] == b"Concurrent remote edit"
    assert b"Updated synthetic lesson" not in github.files(repository)["data.mjs"]


def test_failed_authentication_never_prints_cli_stderr(
    project: Path, github: GitHubFixture
) -> None:
    # Given a GitHub authentication failure containing a synthetic sensitive value.
    github.authentication = False
    # When setup checks the authenticated account.
    result = first_publish(project)
    # Then errors give a login hint without echoing captured CLI output.
    assert isinstance(result.exception, CampusError) and result.exception.code == Code.AUTH_REQUIRED
    assert "synthetic-private-value" not in result.output + str(result.exception)
    assert github.repositories == {}


def test_name_collision_uses_a_stable_suffix(project: Path, github: GitHubFixture) -> None:
    # Given an unrelated repository occupying the proposed name.
    from tum_mcp.study_publish_models import course_identity, repository_name
    from tum_mcp.study_store import load_state

    course = load_state(project).course
    occupied = f"student/{repository_name(course)}"
    original = github.create(occupied)
    # When default-name publication is requested.
    result = first_publish(project)
    # Then a deterministic alternative is chosen and the occupied repository is untouched.
    assert result.exit_code == 0, result.output
    assert load_publication(project).repository == occupied + "-" + course_identity(course)[:8]
    assert github.repositories[occupied] == original and len(github.files(occupied)) == 1


def test_paused_and_local_only_builds_do_not_upload(project: Path, github: GitHubFixture) -> None:
    # Given a configured site with automatic uploads paused.
    assert first_publish(project).exit_code == 0
    assert CliRunner().invoke(app, ["study", "publish", "pause", str(project)]).exit_code == 0
    change_lesson(project)
    count = len(github.requests)
    # When the user builds locally and later opts out of publishing one resumed build.
    result = build(project)
    assert CliRunner().invoke(app, ["study", "publish", "resume", str(project)]).exit_code == 0
    local = CliRunner().invoke(app, ["study", "build", str(project), "--local-only"])
    # Then both local builds remain usable without an upload.
    assert result.publication.status == "paused" and local.exit_code == 0
    assert len(github.requests) == count


def test_launcher_shows_local_hosted_and_repository_links(
    project: Path,
    github: GitHubFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given a published course, with local browser activation isolated.
    assert first_publish(project).exit_code == 0
    saved = load_publication(project)
    monkeypatch.chdir(project)
    monkeypatch.setattr(study_preview.typer, "launch", lambda url: 0)
    monkeypatch.setattr(study_preview, "is_wsl", lambda: False)

    def stop(server: ThreadingHTTPServer) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(ThreadingHTTPServer, "serve_forever", stop)
    count = len(github.requests)
    # When the user starts their normal study session.
    result = CliRunner().invoke(app, ["study", "--port", "0"])
    # Then all links are available without authenticating or republishing.
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:" in result.output and saved.hosted_url in result.output
    assert f"https://github.com/{saved.repository}" in result.output
    assert len(github.requests) == count

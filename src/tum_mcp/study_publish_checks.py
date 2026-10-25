"""Pages configuration and exact-commit deployment verification."""

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_github import Checks, GitHub, Pages, PagesBuild, Status, WorkflowRuns
from tum_mcp.study_publish_models import Publication


def verify_pages(pages: Pages, publication: Publication) -> None:
    if (
        not pages.public
        or pages.source != {"branch": publication.branch, "path": "/"}
        or pages.build_type != "legacy"
    ):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Existing Pages settings need review; they were preserved."
        )


def create_pages(github: GitHub, publication: Publication) -> Pages:
    pages = github.require(
        f"repos/{publication.repository}/pages",
        Pages,
        method="POST",
        payload={
            "build_type": "legacy",
            "source": {"branch": publication.branch, "path": "/"},
        },
    )
    verify_pages(pages, publication)
    return pages


def deployed(github: GitHub, publication: Publication) -> bool:
    """Require this commit's Pages build, workflow runs, checks and statuses to pass."""
    base = f"repos/{publication.repository}"
    latest = github.api(f"{base}/pages/builds/latest", PagesBuild, missing_ok=True)
    if latest is None or latest.commit != publication.commit:
        return False
    if latest.status == "errored":
        raise CampusError(
            Code.ACTION_REQUIRED, "The Pages build failed; inspect the repository's Actions tab."
        )
    if latest.status != "built":
        return False
    runs = github.require(
        f"{base}/actions/runs?head_sha={publication.commit}&per_page=100", WorkflowRuns
    )
    if runs.total_count > len(runs.workflow_runs):
        raise CampusError(
            Code.ACTION_REQUIRED, "Review the remaining workflow runs in GitHub Actions."
        )
    if not runs.workflow_runs or any(run.status != "completed" for run in runs.workflow_runs):
        return False
    if any(run.conclusion != "success" for run in runs.workflow_runs):
        raise CampusError(Code.ACTION_REQUIRED, "GitHub Actions failed for the published commit.")
    checks = github.require(f"{base}/commits/{publication.commit}/check-runs?per_page=100", Checks)
    if checks.total_count > len(checks.check_runs):
        raise CampusError(
            Code.ACTION_REQUIRED, "More than 100 checks need review in GitHub Actions."
        )
    if not checks.check_runs or any(item.status != "completed" for item in checks.check_runs):
        return False
    if any(item.conclusion not in {"success", "neutral", "skipped"} for item in checks.check_runs):
        raise CampusError(Code.ACTION_REQUIRED, "GitHub checks failed for the published commit.")
    status = github.require(f"{base}/commits/{publication.commit}/status", Status)
    if status.total_count and status.state in {"error", "failure"}:
        raise CampusError(
            Code.ACTION_REQUIRED, "A GitHub commit status failed for this publication."
        )
    return not status.total_count or status.state == "success"

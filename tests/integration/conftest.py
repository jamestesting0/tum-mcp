import shutil
from importlib.resources import files
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tum_mcp.cli import app


@pytest.fixture
def inputs(tmp_path: Path) -> Path:
    example = files("tum_mcp") / "bundled/skills/prepare-study/assets/example"
    path = tmp_path / "incoming.json"
    path.write_bytes((example / "snapshot.json").read_bytes())
    return path


@pytest.fixture(scope="session")
def built_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the real synthetic starter once; each test receives a private copy."""
    root = tmp_path_factory.mktemp("study-starter") / "Course space Ω"
    result = CliRunner().invoke(app, ["study", "demo", str(root)])
    assert result.exit_code == 0, result.output
    return root


@pytest.fixture
def project(tmp_path: Path, built_project: Path) -> Path:
    return Path(shutil.copytree(built_project, tmp_path / "Course space Ω"))

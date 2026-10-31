import json
import tarfile
import tomllib
import zipfile

from skill_lab import paths

LEAKS = ("skill-lab", "skill_lab")


def test_npm_allowlist_and_wheel_exclude_the_lab():
    package = json.loads((paths.REPO / "package.json").read_text())
    assert not [entry for entry in package["files"] if any(leak in entry for leak in LEAKS)]
    project = tomllib.loads((paths.REPO / "pyproject.toml").read_text())
    build = project["tool"]["hatch"]["build"]["targets"]
    assert build["wheel"]["packages"] == ["src/tum_mcp"]
    assert "skill-lab" in build["sdist"]["exclude"]
    assert not (paths.REPO / "src" / "tum_mcp" / "skill_lab").exists()


def test_shipped_docs_do_not_mention_the_lab():
    package = json.loads((paths.REPO / "package.json").read_text())
    for entry in package["files"]:
        if entry.endswith(".md"):
            text = (paths.REPO / entry).read_text(encoding="utf-8")
            assert not any(leak in text for leak in LEAKS), entry


def test_built_artifacts_contain_no_lab_files():
    for tarball in sorted((paths.REPO / "dist").glob("*.tgz")):
        with tarfile.open(tarball) as bundle:
            assert not [n for n in bundle.getnames() if any(leak in n for leak in LEAKS)]
    for wheel in sorted((paths.REPO / "npm" / "backend").glob("*.whl")):
        with zipfile.ZipFile(wheel) as bundle:
            assert not [n for n in bundle.namelist() if any(leak in n for leak in LEAKS)]

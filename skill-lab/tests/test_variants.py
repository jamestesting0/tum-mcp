import subprocess

import pytest
from skill_lab import LabError, variants

FILE = "src/tum_mcp/bundled/skills/demo/SKILL.md"


def make_patch(tmp_path, path=FILE):
    for side, text in (("a", "line one\n"), ("b", "line one\nline two\n")):
        target = tmp_path / "make" / side / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    diff = subprocess.run(
        ["git", "diff", "--no-index", f"a/{path}", f"b/{path}"],
        cwd=tmp_path / "make",
        capture_output=True,
        text=True,
    ).stdout
    patch = tmp_path / "change.patch"
    patch.write_text(diff.replace("a/a/", "a/").replace("b/b/", "b/"))
    return patch


def test_patch_applies_inside_a_copy_nested_in_another_repository(tmp_path):
    outer = tmp_path / "outer"
    subprocess.run(["git", "init", "-q", str(outer)], check=True)
    repo = outer / ".omo" / "variant" / "repo"
    (repo / FILE).parent.mkdir(parents=True)
    (repo / FILE).write_text("line one\n")
    variants.apply_patch(make_patch(tmp_path), repo)
    assert (repo / FILE).read_text() == "line one\nline two\n"


def test_patches_outside_the_package_or_into_guarded_code_are_refused(tmp_path):
    with pytest.raises(LabError, match="only change files under src/tum_mcp"):
        variants.check_patch(make_patch(tmp_path, "docs/study.md"))
    with pytest.raises(LabError, match="campus, session"):
        variants.check_patch(make_patch(tmp_path, "src/tum_mcp/moodle/service.py"))

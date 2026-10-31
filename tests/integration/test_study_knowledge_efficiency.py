"""Deterministic work regressions; timings are explicit local evidence, never a CI gate."""

import json
import os
from pathlib import Path

import pytest
from course_memory_profile import profile, scaled_course

from tum_mcp.study_knowledge_store import load_inputs

pytestmark = pytest.mark.usefixtures("course_memory")


def test_crowded_profile_respects_native_schema_and_snapshot(tmp_path: Path):
    root = scaled_course(tmp_path, 10, crowded=True)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    inputs = load_inputs(root)
    assert len(inputs.study.units) == 10
    assert all(len(u.blocks) == 20 for u in inputs.study.units)
    inputs.reader.verify()
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.skipif(
    os.environ.get("TUM_MCP_MEMORY_PROFILE") != "1", reason="local profiling opt-in"
)
def test_profile_course_memory(tmp_path: Path):
    output = Path(os.environ["TUM_MCP_MEMORY_PROFILE_OUTPUT"]).resolve()
    repo = Path(__file__).resolve().parents[2]
    assert output.is_relative_to(repo / ".omo/evidence/course-memory-optimization")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile(tmp_path), indent=2), encoding="utf-8")

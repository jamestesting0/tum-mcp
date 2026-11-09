import json

import pytest
from skill_lab import LabError
from skill_lab.memory_bench import TEACHING, metrics
from skill_lab.memory_bench_agent import cited, grade, plan_stage, protected_changes

NAMES = {
    "problem-1-2-1": {"exercises/set/s/exercise/problem-1-2-1"},
    "rational actions": {"exercises/set/s/exercise/problem-1-1-1"},
    "agents#peas": {"study/unit/agents/block/peas"},
    "peas": {"study/unit/agents/block/peas"},
    "past:3a": {"exam/sitting/m/variant/v/question/3a"},
    "slides-1": {"source/slides-1"},
}


def test_sources_line_maps_keys_titles_and_pages_to_item_refs():
    text = (
        "Answer.\nSOURCES: exercise:problem-1-2-1, lesson:agents#peas, past:3a, "
        "slides:slides-1#20, x:y"
    )
    refs, unmatched, none = cited(text, NAMES)
    assert refs == {
        "exercises/set/s/exercise/problem-1-2-1",
        "study/unit/agents/block/peas",
        "exam/sitting/m/variant/v/question/3a",
        "source/slides-1",
    }
    assert unmatched == ["x:y"] and not none


def test_grade_requires_every_gold_ref_and_rejects_forbidden_ones():
    task = {
        "required": ["study/unit/agents/block/peas", "source/slides-1"],
        "forbidden": ["source/slides-1"],
    }
    partial = grade(task | {"forbidden": []}, "SOURCES: lesson:agents#peas", NAMES)
    assert not partial["success"] and partial["recall"] == 0.5
    forbidden = grade(task, "SOURCES: lesson:agents#peas, slides:slides-1#2", NAMES)
    assert not forbidden["success"] and forbidden["forbidden"] == ["source/slides-1"]


def test_owner_level_gold_accepts_a_cited_entry_of_that_owner():
    task = {"required": ["study/unit/agents"], "owner_level": True}
    assert grade(task, "SOURCES: lesson:agents#peas", NAMES)["success"]


def test_absent_topic_passes_only_with_sources_none():
    task = {"none": True}
    assert grade(task, "Not covered.\nSOURCES: none", NAMES)["success"]
    assert not grade(task, "SOURCES: lesson:agents#peas", NAMES)["success"]


def test_protected_changes_flag_content_and_memory_writes_but_not_caches():
    before = {"app/study/course.json": "a", ".tum-mcp/cache/x": "b"}
    after = {
        "app/study/course.json": "a2",
        ".tum-mcp/cache/x": "b2",
        ".tum-mcp/knowledge.json": "new",
        ".tum-mcp/notes/finding.md": "n",
    }
    assert protected_changes(before, after) == [".tum-mcp/knowledge.json", "app/study/course.json"]


def test_stage_two_repeats_only_tasks_whose_arms_disagree():
    tasks = [{"id": "R1"}, {"id": "R2"}]
    rows = [
        {"task": "R1", "arm": "A", "trial": 1, "success": True},
        {"task": "R1", "arm": "B", "trial": 1, "success": False},
        {"task": "R2", "arm": "A", "trial": 1, "success": True},
        {"task": "R2", "arm": "B", "trial": 1, "success": True},
    ]
    assert plan_stage(rows, tasks, 2) == [
        ("R1", "A", 2),
        ("R1", "A", 3),
        ("R1", "B", 2),
        ("R1", "B", 3),
    ]
    assert plan_stage(rows, tasks, 1) == []


def test_stage_refuses_to_exceed_the_episode_cap():
    tasks = [{"id": f"T{n}"} for n in range(40)]
    with pytest.raises(LabError):
        plan_stage([], tasks, 1)


def test_direct_fill_reserves_the_seed_slot_and_counts_displacement(tmp_path):
    seed, links = "exam/concept/c", ["exercises/set/s/exercise/a", "exercises/set/s/exercise/b"]
    cases = {
        "fill": [
            {"seed": seed, "purpose": "exercises", "direct": links, "selector": "full"},
            {"seed": seed, "purpose": "exercises", "direct": links, "selector": "weak"},
        ],
        "recall": [],
        "impact": [],
        "statements": [],
        "written": [],
        "cited": {},
    }
    item = lambda ref: {"id": ref, "locators": []}  # noqa: E731
    packets = {
        "full": {"items": [item(seed), item(links[0]), item(links[1])]},
        "weak": {"items": [item(seed), item(links[0]), item("study/unit/u")]},
    }
    for name, value in (
        ("cases", cases),
        ("packets", packets),
        ("mutations", []),
        ("timing", {"seconds": [0.1]}),
    ):
        (tmp_path / f"{name}.json").write_text(json.dumps(value))
    result = metrics(tmp_path)["direct_fill_at_4"]
    assert TEACHING["limit"] == 4
    assert result["mean"] == 0.75 and result["displaced"] == 1

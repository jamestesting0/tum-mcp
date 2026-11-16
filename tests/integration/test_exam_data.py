import json
from pathlib import Path

import pytest
from material_fixture import exam_document, exam_project, pdf_bytes

from tum_mcp.course.content.exam import Concept, ExamContent
from tum_mcp.course.content.exam_data import exam_report, exam_statistics, stale_exam
from tum_mcp.course.content.exam_layout import NODE_GAP, NODE_WIDTH, layout
from tum_mcp.course.project.store import load_state


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return exam_project(tmp_path_factory.mktemp("exam-data"))


@pytest.fixture(scope="module")
def content(project: Path) -> ExamContent:
    return ExamContent.model_validate(exam_document(project))


def test_current_past_questions_need_prepared_guidance(project: Path) -> None:
    from material_fixture import with_guided_paper

    from tum_mcp.course.content.exam_data import practice_flags

    raw = exam_document(project)
    before = practice_flags(ExamContent.model_validate(raw))
    assert any("ws23-a-1" in flag["detail"] for flag in before)
    after = practice_flags(ExamContent.model_validate(with_guided_paper(raw)))
    assert not any("ws23-a-1" in flag["detail"] for flag in after)


def test_workflow_expansions_must_add_to_the_step_or_case(project: Path) -> None:
    from tum_mcp.course.content.exam_data import practice_flags

    raw = exam_document(project)
    steps = raw["patterns"][0]["workflow"]
    steps[0]["apply"] = {"text": steps[0]["do"] + "."}
    case = steps[1]["cases"][0]
    case["apply"] = {"text": case["then"]}
    flags = practice_flags(ExamContent.model_validate(raw))
    repeats = [flag for flag in flags if flag["flag"] == "redundant_workflow_detail"]
    assert len(repeats) == 2
    assert all(flag["item"] == "exam/pattern/observer-design" for flag in repeats)

    steps[0]["apply"] = {"text": "The subject owns state; observers react to its changes."}
    case["apply"] = {"text": case["then"], "code": "o.update(state)", "language": "java"}
    assert not any(
        flag["flag"] == "redundant_workflow_detail"
        for flag in practice_flags(ExamContent.model_validate(raw))
    )


def test_exam_retrieval_does_not_expand_a_bounded_study_request(project: Path) -> None:
    from material_fixture import minimal_unit

    from tum_mcp.course.content.exam_data import retrieval_flags
    from tum_mcp.course.content.study import StudyContent

    raw = exam_document(project)
    raw["concepts"][0]["units"] = ["observer"]
    slides = raw["concepts"][0]["sources"][0]
    unit = minimal_unit("observer", slides["key"], slides["sha256"])
    study = {
        "course_key": raw["course_key"],
        "organization": "topics",
        "introduction": "Observer only.",
        "units": [unit],
    }
    flags = retrieval_flags(ExamContent.model_validate(raw), StudyContent.model_validate(study))
    assert {flag["item"] for flag in flags} == {"concept:observer"}
    unit["flashcards"][0].update(
        front="What does Observer mean?",
        back="Subjects notify registered observers when state changes.",
    )
    assert (
        retrieval_flags(ExamContent.model_validate(raw), StudyContent.model_validate(study)) == []
    )


def test_frequencies_count_each_exam_once_and_skip_outdated_sittings(content: ExamContent) -> None:
    stats = exam_statistics(content)
    observer = stats["patterns"]["observer-design"]
    assert (observer["sittings_seen"], observer["sittings_considered"]) == (2, 2)
    assert (observer["variants_seen"], observer["variants_considered"]) == (3, 3)
    assert observer["last_seen"] == "2024-02" and observer["last_label"] == "Endterm WS23/24"
    strategy = stats["patterns"]["strategy-swap"]
    assert (strategy["sittings_seen"], strategy["variants_seen"]) == (1, 2)
    assert stats["pattern_order"] == ["observer-design", "composite-tree", "strategy-swap"]
    assert stats["points_known"] is False and observer["points_share"] is None
    assert stats["sittings_outdated"] == 1 and stats["years"] == ["2023", "2024"]
    assert stats["topic_shares"] == {
        "basis": "questions",
        "shares": {"behavioral": 0.8333, "structural": 0.1667},
    }
    assert stats["concepts"]["observer"]["sittings_seen"] == 2
    instances = {item["question"] for item in observer["instances"]}
    assert instances == {"ws23-a-1", "ws23-b-1", "ws22-1"}


def test_report_flags_targets_and_review_items_without_enforcing_them(content: ExamContent) -> None:
    report = exam_report(content)
    flags = {(item["item"], item["measure"]) for item in report["targets"]}
    assert ("mock:forecast-1", "estimated minutes vs duration") in flags
    assert ("mock:forecast-1", "points vs the real exam") in flags
    assert ("mock:forecast-1", "topic share gap (behavioral)") in flags
    # Every pattern now has practice, so only the unpatterned concept stays uncovered.
    assert report["uncovered_core"] == ["cohesion"]
    assert {item["question"] for item in report["review"]} == {"ws22-2", "ss19-1"}
    mock = report["blueprint"]["mocks"][0]
    assert mock["points"] == 18 and mock["novelty"] == {"variant": 1, "untested": 1}
    json.dumps(report)


def test_workflow_from_names_a_pattern_that_lists_the_concept(project: Path) -> None:
    document = exam_document(project)
    pattern = document["patterns"][0]
    listed = pattern["concepts"][0]
    other = next(c for c in document["concepts"] if c["key"] not in pattern["concepts"])
    for concept in document["concepts"]:
        if concept["key"] in {listed, other["key"]}:
            concept["workflow_from"] = pattern["key"]
    with pytest.raises(ValueError, match="does not list it"):
        ExamContent.model_validate(document)
    other.pop("workflow_from")
    assert ExamContent.model_validate(document)


def test_one_line_fact_passes_but_a_method_without_steps_is_flagged(
    content: ExamContent,
) -> None:
    # A pattern merely listing a procedure no longer counts as its steps: only details or
    # workflow_from put steps in the entry.
    concept = next(
        concept
        for concept in content.concepts
        if any(concept.key in pattern.concepts for pattern in content.patterns)
    )
    bare = {"formula": None, "trigger": None, "pitfall": None, "details": ()}
    fact = concept.model_copy(update={**bare, "kind": "fact"})
    method = concept.model_copy(update={**bare, "kind": "procedure", "workflow_from": None})
    measures = {
        kind: {
            flag["measure"]
            for flag in exam_report(
                content.model_copy(
                    update={
                        "concepts": tuple(
                            item if c.key == concept.key else c for c in content.concepts
                        )
                    }
                )
            )["targets"]
            if flag["item"] == f"concept:{concept.key}"
        }
        for kind, item in (("fact", fact), ("method", method))
    }
    assert "procedure entry without steps" not in measures["fact"]
    assert "procedure entry without steps" in measures["method"]


def test_layout_is_deterministic_layered_and_non_overlapping(content: ExamContent) -> None:
    first, second = layout(content), layout(content)
    assert first == second
    nodes = {node["key"]: node for node in first["nodes"]}
    assert set(nodes) == {"observer", "loose-coupling", "strategy", "composite", "decorator"}
    assert nodes["loose-coupling"]["depth"] == 0 and nodes["observer"]["depth"] == 1
    assert nodes["decorator"]["depth"] == 0
    regions = first["regions"]
    assert [region["topic"] for region in regions] == ["behavioral", "structural"]
    # Each idea sits inside its topic's region, below the title band, and regions never overlap.
    for one, other in zip(regions, regions[1:], strict=False):
        assert one["x"] + one["width"] <= other["x"] or one["y"] + one["height"] <= other["y"]
    rows: dict[tuple[int, int], list[int]] = {}
    for node in first["nodes"]:
        rows.setdefault((node["column"], node["y"]), []).append(node["x"])
        box = regions[node["column"]]
        assert box["x"] <= node["x"] and node["x"] + NODE_WIDTH <= box["x"] + box["width"]
        assert box["y"] + first["header"] <= node["y"]
        assert node["y"] + first["node_height"] <= box["y"] + box["height"] <= first["height"]
    for xs in rows.values():
        xs.sort()
        assert all(
            right - left >= NODE_WIDTH + NODE_GAP for left, right in zip(xs, xs[1:], strict=False)
        )
    assert first["overview"]["links"] == []


def test_a_wrapped_band_keeps_a_link_clear_of_other_cards() -> None:
    # A pilot map wrapped four first-row ideas into two rows and drew an arrow through the
    # second row; the idea with a link below now sits in the band's last row.
    from importlib.resources import files

    exam = json.loads((files("tum_mcp") / "bundled/course_app/example/exam.json").read_bytes())
    for concept in exam["concepts"]:
        if concept["key"] in {"operation-costs", "removal-matrix"}:
            concept["on_map"] = True
    nodes = {node["key"]: node for node in layout(ExamContent.model_validate(exam))["nodes"]}
    source, target = nodes["fifo"], nodes["queue"]
    assert source["depth"] == 0 and target["depth"] == 1
    between = [
        key
        for key, node in nodes.items()
        if node["column"] == source["column"] and source["y"] < node["y"] < target["y"]
    ]
    assert between == []


def test_changed_sources_mark_only_dependent_items_stale(tmp_path: Path) -> None:
    root = exam_project(tmp_path)
    content = ExamContent.model_validate(exam_document(root))
    assert stale_exam(root, load_state(root), content) == ()
    (root / "materials/exams/material-exam-ws22-upload.pdf").write_bytes(pdf_bytes(["Edited"]))
    assert stale_exam(root, load_state(root), content) == ("variant:ws22-a",)


def test_cheatsheet_typed_math_and_slash_quotients_are_prompts(content: ExamContent) -> None:
    # The FAI pilot typed λ and ≥ into pitfalls and wrote displayed quotients with slashes;
    # nothing reported either. Units and derivatives keep their slash.
    from tum_mcp.course.checks.report import slash_quotients
    from tum_mcp.course.content.exam_data import sheet_flags

    concept = next(c for c in content.concepts if c.formula)
    typed = concept.model_copy(
        update={
            "pitfall": "Only for λ > 0.",
            "formula": concept.formula.model_copy(update={"latex": "v = d/n"}),
            "line": "Speed: \\(v = d/n\\).",
        }
    )
    changed = content.model_copy(
        update={"concepts": tuple(typed if c.key == concept.key else c for c in content.concepts)}
    )
    flags = {(f["item"], f["flag"]) for f in sheet_flags(changed)}
    assert (f"concept:{concept.key}", "sheet_plain_math") in flags
    assert (f"concept:{concept.key}", "slash_quotient") in flags
    assert (f"concept:{concept.key}", "line_repeats_formula") in flags
    assert slash_quotients(r"v = 3\,\mathrm{m/s},\quad \frac{d}{dx} = d/dx") == []


def test_entry_meanings_and_prose_prompts_for_non_formula_entries(content: ExamContent) -> None:
    # The FAI pilot typed its variable meanings as a dense sentence beside a table, and nothing
    # reported it; a non-formula entry had no way to list them.
    from tum_mcp.course.content.exam_data import sheet_flags
    from tum_mcp.course.content.study import Symbol, TextBlock

    concept = next(c for c in content.concepts if not c.formula)
    source = concept.sources[0].key
    legend = TextBlock(
        kind="text",
        sources=(source,),
        paragraphs=(
            "\\(b\\): maximum branching, \\(d\\): shallowest goal depth. These bounds assume "
            "\\(b \\ge 2\\). Memory bounds assume tree search. Here c is any step cost.",
        ),
    )
    data = concept.model_dump(mode="json") | {"details": [legend.model_dump(mode="json")]}
    listed = Concept.model_validate(
        data | {"symbols": [{"symbol": "\\(b\\)", "meaning": "maximum branching factor"}]}
    )
    assert listed.symbols == (Symbol(symbol="\\(b\\)", meaning="maximum branching factor"),)
    with pytest.raises(ValueError, match="does not appear"):
        Concept.model_validate(data | {"symbols": [{"symbol": "\\(q\\)", "meaning": "x"}]})
    changed = content.model_copy(
        update={"concepts": tuple(listed if c.key == concept.key else c for c in content.concepts)}
    )
    flags = {f["flag"] for f in sheet_flags(changed) if f["item"] == f"concept:{concept.key}"}
    assert {"sheet_dense_paragraph", "prose_legend"} <= flags

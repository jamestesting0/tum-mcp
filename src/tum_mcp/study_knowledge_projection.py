"""Project explicit workspace relationships without inventing concept equivalence."""

from tum_mcp.study_content import SourceVersion, term_markers
from tum_mcp.study_knowledge_graph import Edge, Graph, Node, block_records, safe_text
from tum_mcp.study_knowledge_models import LectureEvidence, SourceEvidence, normalized
from tum_mcp.study_knowledge_store import CourseInputs


def project(inputs: CourseInputs) -> Graph:
    graph = Graph(inputs)
    for key in inputs.resources:
        graph.source(key)
    _study(graph)
    _exercises(graph)
    _exam(graph)
    _lectures(graph)
    _links(graph)
    _registry(graph)
    return graph


def _study(graph: Graph) -> None:
    content = graph.inputs.study
    if content is None:
        return
    for unit in content.units:
        body = unit.model_dump(mode="json")
        sources = (*unit.sources, *(s for item in unit.explore for s in item.sources))
        owner = graph.add(
            Node(
                f"study/unit/{unit.key}",
                "study",
                "unit",
                unit.title,
                unit.summary,
                safe_text({"blocks": body["blocks"], "objectives": body["objectives"]}),
                body,
                sources,
                {
                    "role": "core",
                    "context": {"title": unit.title, "objectives": body["objectives"]},
                },
                "owner",
            )
        )
        graph.passages(owner, body["blocks"])
        for kind, items in (("question", unit.questions), ("flashcard", unit.flashcards)):
            for item in items:
                value = item.model_dump(mode="json")
                prompt = value.get("prompt") or value.get("front") or item.key
                child = graph.add(
                    Node(
                        f"{owner.id}/{kind}/{item.key}",
                        "study",
                        kind,
                        str(prompt),
                        "",
                        str(prompt),
                        value,
                        unit.sources,
                        owner.scope,
                    )
                )
                graph.connect(Edge(owner.id, child.id, "contains"))
        for item in unit.explore:
            value = item.model_dump(mode="json")
            child = graph.add(
                Node(
                    f"{owner.id}/explore/{item.key}",
                    "study",
                    "explore",
                    item.title,
                    "",
                    safe_text(value),
                    value,
                    item.sources,
                    {"role": "enrichment"},
                    "owner",
                )
            )
            graph.passages(child, value["blocks"])
            graph.connect(Edge(owner.id, child.id, "contains"))


def _exercises(graph: Graph) -> None:
    content = graph.inputs.exercises
    if content is None:
        return
    for group in content.sets:
        for exercise in group.exercises:
            value = exercise.model_dump(mode="json")
            owner = graph.add(
                Node(
                    f"exercises/set/{group.key}/exercise/{exercise.key}",
                    "exercises",
                    "exercise",
                    exercise.title,
                    " ".join(exercise.objectives),
                    safe_text(value["statement"]),
                    value,
                    exercise.sources,
                    {
                        "role": "core",
                        "origin": exercise.kind,
                        "solution_origin": exercise.solution.origin,
                        "context": {
                            "statement": value["statement"],
                            "objectives": value["objectives"],
                            "part_blocks": dict(exercise.part_blocks),
                        },
                    },
                    "owner",
                )
            )
            for step in exercise.steps:
                child = graph.add(
                    Node(
                        f"{owner.id}/step/{step.key}",
                        "exercises",
                        "step",
                        step.purpose,
                        step.prompt,
                        step.prompt,
                        step.model_dump(mode="json"),
                        exercise.sources,
                        owner.scope,
                    )
                )
                graph.connect(Edge(owner.id, child.id, "contains"))


def _exam(graph: Graph) -> None:
    exam = graph.inputs.exam
    if exam is None:
        return
    for kind, items in (("concept", exam.concepts), ("pattern", exam.patterns)):
        for item in items:
            value = item.model_dump(mode="json")
            summary = str(value.get("line") or value.get("summary") or "")
            graph.add(
                Node(
                    f"exam/{kind}/{item.key}",
                    "exam",
                    kind,
                    item.title,
                    summary,
                    safe_text(value),
                    value,
                    item.sources,
                    {"role": "core", "origin": "authored"},
                )
            )
    for sitting in exam.sittings:
        for variant in sitting.variants:
            refs = tuple(SourceVersion(key=s.key, sha256=s.sha256) for s in variant.sources)
            scope = {
                "role": "core",
                "origin": "past",
                "relevance": sitting.relevance,
                "source_roles": [s.model_dump(mode="json") for s in variant.sources],
            }
            owner = graph.add(
                Node(
                    f"exam/sitting/{sitting.key}/variant/{variant.key}",
                    "exam",
                    "variant",
                    sitting.label + ": " + variant.label,
                    "",
                    "",
                    variant.model_dump(mode="json"),
                    refs,
                    scope,
                    "owner",
                )
            )
            for question in variant.questions:
                value = question.model_dump(mode="json")
                child = graph.add(
                    Node(
                        f"{owner.id}/question/{question.key}",
                        "exam",
                        "past_question",
                        f"{sitting.label}, question {question.number}",
                        "",
                        safe_text(value["statement"]),
                        value,
                        refs,
                        scope
                        | {"classification": question.status, "question_number": question.number},
                    )
                )
                graph.connect(Edge(owner.id, child.id, "contains"))
    for mock in exam.mocks:
        owner = graph.add(
            Node(
                f"exam/mock/{mock.key}",
                "exam",
                "mock",
                mock.title,
                "",
                "",
                mock.model_dump(mode="json"),
                mock.sources,
                {"role": "core", "origin": "synthetic"},
                "owner",
            )
        )
        for question in mock.questions:
            value = question.model_dump(mode="json")
            child = graph.add(
                Node(
                    f"{owner.id}/question/{question.key}",
                    "exam",
                    "mock_question",
                    f"{mock.title}, question {question.number}",
                    "",
                    safe_text(value["statement"]),
                    value,
                    mock.sources,
                    owner.scope | {"question_number": question.number},
                )
            )
            graph.connect(Edge(owner.id, child.id, "contains"))


def _lectures(graph: Graph) -> None:
    content = graph.inputs.lectures
    if content is None:
        return
    for lecture in content.lectures:
        scope = {
            "role": "core",
            "lecture": lecture.key,
            "recording": lecture.recording.model_dump(mode="json"),
            "coverage": lecture.coverage.model_dump(mode="json"),
        }
        owner = graph.add(
            Node(
                f"lectures/lecture/{lecture.key}",
                "lectures",
                "lecture",
                lecture.title,
                lecture.overview,
                " ".join(lecture.takeaways),
                lecture.model_dump(mode="json"),
                lecture.sources,
                scope,
                "owner",
            )
        )
        for section in lecture.sections:
            value = section.model_dump(mode="json")
            child = graph.add(
                Node(
                    f"{owner.id}/section/{section.key}",
                    "lectures",
                    "section",
                    section.title,
                    "",
                    safe_text(value["blocks"]),
                    value,
                    lecture.sources,
                    scope,
                )
            )
            graph.connect(Edge(owner.id, child.id, "contains"))


def _links(graph: Graph) -> None:
    if study := graph.inputs.study:
        definitions: dict[str, str] = {}
        for unit in study.units:
            owner = f"study/unit/{unit.key}"
            for block in block_records([b.model_dump(mode="json") for b in unit.blocks]):
                if block.get("kind") == "definition" and isinstance(block.get("term"), str):
                    ref = f"{owner}/block/{block.get('key')}"
                    definitions[normalized(block["term"])] = ref if ref in graph.nodes else owner
            for lecture in unit.lectures:
                graph.connect(Edge(owner, f"lectures/lecture/{lecture}", "linked_lecture"))
        for unit in study.units:
            for term in term_markers(unit.model_dump(mode="json")):
                if target := definitions.get(normalized(term)):
                    if target != f"study/unit/{unit.key}":
                        graph.connect(Edge(f"study/unit/{unit.key}", target, "mentions", "lexical"))
    if content := graph.inputs.exercises:
        for group in content.sets:
            for exercise in group.exercises:
                for ref in exercise.prerequisites:
                    foundation = f"study/unit/{ref.unit}" + (
                        f"/block/{ref.block}" if ref.block else ""
                    )
                    graph.connect(
                        Edge(
                            foundation,
                            f"exercises/set/{group.key}/exercise/{exercise.key}",
                            "prerequisite_of",
                        )
                    )
    if exam := graph.inputs.exam:
        for concept in exam.concepts:
            for unit in concept.units:
                graph.connect(
                    Edge(f"exam/concept/{concept.key}", f"study/unit/{unit}", "linked_teaching")
                )
        for link in exam.links:
            graph.connect(
                Edge(
                    f"exam/concept/{link.start}",
                    f"exam/concept/{link.end}",
                    "prerequisite_of" if link.kind == "requires" else link.kind,
                )
            )
        for pattern in exam.patterns:
            for concept in pattern.concepts:
                graph.connect(
                    Edge(f"exam/pattern/{pattern.key}", f"exam/concept/{concept}", "uses_concept")
                )
        for node in tuple(graph.nodes.values()):
            if node.kind in {"past_question", "mock_question"} and isinstance(node.payload, dict):
                for kind in ("concept", "pattern"):
                    for key in node.payload.get(kind + "s", []):
                        graph.connect(
                            Edge(
                                node.id,
                                f"exam/{kind}/{key}",
                                "assesses" if kind == "concept" else "uses_pattern",
                            )
                        )
    if ledger := graph.inputs.ledger:
        for entry in ledger.sources:
            for outcome in entry.outcomes:
                node = graph.add(
                    Node(
                        f"coverage/{entry.source}/{outcome.key}",
                        "coverage",
                        "outcome",
                        outcome.text,
                        "",
                        "",
                        outcome.model_dump(mode="json"),
                        scope={
                            "role": outcome.role,
                            "status": outcome.status,
                            "availability": entry.status.availability,
                        },
                    )
                )
                graph.connect(Edge(node.id, graph.source(entry.source), "coverage_of"))
                for unit in outcome.units:
                    graph.connect(Edge(node.id, f"study/unit/{unit}", "covered_by"))
                for ref in outcome.explore:
                    graph.connect(
                        Edge(node.id, f"study/unit/{ref.unit}/explore/{ref.item}", "covered_by")
                    )


def _registry(graph: Graph) -> None:
    registry = graph.inputs.registry
    if registry is None:
        return
    for concept in registry.concepts:
        graph.add(
            Node(
                f"concept/{concept.key}",
                "concept",
                "concept",
                concept.label,
                concept.summary,
                " ".join(concept.aliases),
                concept.model_dump(mode="json"),
                scope={"role": "navigation"},
            )
        )
    for assertion in registry.assertions:
        graph.assertions[assertion.key] = assertion
        for group in assertion.support_groups:
            for evidence in group.evidence:
                match evidence:
                    case SourceEvidence():
                        graph.source(evidence.source)
                    case LectureEvidence():
                        pass
        if assertion.review.status == "reviewed":
            graph.connect(
                Edge(
                    assertion.start.node_id,
                    assertion.end.node_id,
                    assertion.relation,
                    "reviewed",
                    assertion.key,
                    assertion.conditions,
                )
            )

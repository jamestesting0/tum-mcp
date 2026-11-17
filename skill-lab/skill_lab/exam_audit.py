"""Deterministic facts about a run's Exam workspace, for judging prepare-exams rounds.

Course-specific expectations (which sittings exist, which held-out questions matter) stay in
the private round notes; this module only counts what the workspace holds.
"""

from collections import Counter
from pathlib import Path

from tum_mcp.course.content.exam import ExamContent
from tum_mcp.course.content.exam_data import read_exam


def audit_content(exam: ExamContent) -> dict[str, object]:
    past = exam.past_questions()
    statuses = Counter(question.status for _, _, question in past.values())
    classified = [q for _, _, q in past.values() if q.status == "classified"]
    instances: Counter[str] = Counter()
    for question in classified:
        instances.update(question.patterns)
    patterns = {
        pattern.key: {
            "past_instances": instances[pattern.key],
            "decision_steps": sum(1 for step in pattern.workflow if getattr(step, "cases", ())),
            "steps": len(pattern.workflow),
            "examples": len(pattern.examples),
            "drill": len(pattern.drill),
            "pitfalls": len(pattern.pitfalls),
        }
        for pattern in exam.patterns
    }
    linked_concepts = {
        *(key for pattern in exam.patterns for key in pattern.concepts),
        *(key for mock in exam.mocks for question in mock.questions for key in question.concepts),
    }
    return {
        "sittings": [
            {
                "key": sitting.key,
                "kind": sitting.kind,
                "relevance": sitting.relevance,
                "variants": len(sitting.variants),
                "roles": sorted(
                    {source.role for variant in sitting.variants for source in variant.sources}
                ),
                "questions": sum(len(variant.questions) for variant in sitting.variants),
            }
            for sitting in exam.sittings
        ],
        "question_status": dict(statuses),
        "classified_without_pattern": sorted(q.key for q in classified if not q.patterns),
        "classified_without_guidance": sorted(
            q.key for q in classified if getattr(q, "guidance", None) is None
        ),
        "patterns": patterns,
        "single_instance_patterns": sorted(
            k for k, v in patterns.items() if v["past_instances"] <= 1
        ),
        "concepts": {
            "total": len(exam.concepts),
            "by_basis": dict(Counter(concept.basis for concept in exam.concepts)),
            "by_kind": dict(Counter(concept.kind for concept in exam.concepts)),
            "core_untrained": sorted(
                concept.key
                for concept in exam.concepts
                if concept.tier == "core" and concept.key not in linked_concepts
            ),
            "with_study_link": sum(1 for c in exam.concepts if c.units or c.passages),
        },
        "mocks": [
            {
                "key": mock.key,
                "minutes": mock.duration_minutes,
                "questions": len(mock.questions),
                "novelty": dict(Counter(q.novelty for q in mock.questions)),
                "points": sum(q.points for q in mock.questions),
            }
            for mock in exam.mocks
        ],
    }


def audit(project: Path) -> dict[str, object] | None:
    exam = read_exam(project)
    return None if exam is None else audit_content(exam)

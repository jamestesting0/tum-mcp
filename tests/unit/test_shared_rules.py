import json
from importlib.resources import files
from pathlib import Path

from tum_mcp.course.checks.report import foreign_language, language_flags
from tum_mcp.course.content.study import StudyContent
from tum_mcp.course.project.context import content_language

SKILLS = Path(str(files("tum_mcp") / "bundled/skills"))
AUTHORING = {"prepare-study", "prepare-exercises", "prepare-exams", "prepare-lecture"}
FIXTURES = Path(__file__).parents[1] / "fixtures"


def _passages(marker: str, skills: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(SKILLS / name / "SKILL.md" for name in skills):
        for paragraph in path.read_text(encoding="utf-8").split("\n\n"):
            if paragraph.lstrip().startswith(marker):
                found[path.parent.name] = " ".join(paragraph.split())
    return found


def test_copied_skill_passages_stay_identical() -> None:
    # Authors read SKILL.md and rarely open references, so these rules are copied on purpose.
    for marker in (
        "Write in the course's content language",
        "**Maths.**",
        "| Write | Not |",
    ):
        passages = _passages(marker, AUTHORING)
        assert passages.keys() == AUTHORING, (marker, sorted(AUTHORING - passages.keys()))
        assert len(set(passages.values())) == 1, (marker, sorted(passages))


GERMAN = (
    "Die Suche wird mit dem Startknoten begonnen, und der Knoten mit den kleinsten Kosten "
    "wird zuerst erweitert. Das ist nicht immer die beste Wahl, denn die Kosten sind auch "
    "von dem Ziel und von der Heuristik abhängig, die wir für jeden Knoten berechnen."
)


def test_text_in_another_language_than_the_course_is_recognised() -> None:
    assert foreign_language(GERMAN, "en") == "de"
    assert foreign_language(GERMAN, "de") is None
    # Then clean English content in an English course raises no flag, nor does an unrecorded one.
    english = StudyContent.model_validate(
        json.loads((FIXTURES / "course_app/content.json").read_bytes())
    )
    assert not language_flags("en", english, None, None)
    assert not language_flags(None, english, None, None)


def test_every_check_named_in_skill_text_is_registered() -> None:
    import re

    from tum_mcp.course.review.media import COMMON_CHECKS, PROFILE_CHECKS
    from tum_mcp.course.review.registry import checks

    known = set(checks()) | set(COMMON_CHECKS).union(*PROFILE_CHECKS.values())
    named = {
        found
        for path in SKILLS.glob("*/**/*.md")
        for found in re.findall(
            r"`((?:correctness|clarity|cohesion|cognitive_load|representation|practice|coverage|"
            r"intuition|organization|redundancy|integration|synchronization|delivery)\.[a-z_]+)`",
            path.read_text(encoding="utf-8"),
        )
    }
    assert named and not sorted(named - known)


def test_the_content_language_is_read_from_the_course_handbook(tmp_path: Path) -> None:
    folder = tmp_path / ".tum-mcp"
    folder.mkdir()
    (folder / "course.md").write_text(
        "---\ncourse_key: c\nsemester: ws\ncontent_language: de\n---\n# C\n", encoding="utf-8"
    )
    assert content_language(tmp_path) == "de"
    (folder / "course.md").write_text("# No header\n", encoding="utf-8")
    assert content_language(tmp_path) is None

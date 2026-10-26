import pytest

from tum_mcp.studocu.discovery import classify


@pytest.mark.parametrize(
    "title,description,expected",
    [
        ("Klausurlösung 2023", "", ("exams", "solution")),
        ("Musterlösung zur Klausur", "", ("exams", "solution")),
        ("Probeklausur mit Lösung", "", ("exams", "solution")),
        ("Zusammenfassung zur Klausur", "", ("summaries", "summary")),
        ("Formula sheet", "Useful for the exam", ("summaries", "summary")),
        ("Old exam", "", ("exams", "exam")),
        ("Mock exam", "", ("exams", "mock")),
        ("Course overview", "", ("other", "other")),
    ],
)
def test_bilingual_candidate_classification(
    title: str, description: str, expected: tuple[str, str]
) -> None:
    assert classify(title, description) == expected

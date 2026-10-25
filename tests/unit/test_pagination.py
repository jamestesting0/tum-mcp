import pytest

from tum_mcp.moodle.errors import MoodleError
from tum_mcp.moodle.models import Extracted, TextPage
from tum_mcp.moodle.pagination import excerpt, offset_of


def test_continuation_preserves_selected_page_range() -> None:
    content = Extracted(pages=[TextPage(number=1, text="wrong"), TextPage(number=2, text="abcdef")])
    first = excerpt(content, None, 3, 2, 2)
    second = excerpt(content, first["next_cursor"], 3, None, None)
    assert second["pages"] == [{"number": 2, "unit": "page", "text": "def"}]
    assert second["next_cursor"] is None


def test_changed_document_invalidates_cursor() -> None:
    first = excerpt(Extracted(pages=[TextPage(number=1, text="abcdef")]), None, 3, None, None)
    with pytest.raises(MoodleError):
        excerpt(
            Extracted(pages=[TextPage(number=1, text="changed")]),
            first["next_cursor"],
            3,
            None,
            None,
        )


@pytest.mark.parametrize("cursor", ["²", "١", "-1", "abc", "", "12345678"])
def test_invalid_offset_returns_an_actionable_error(cursor: str) -> None:
    with pytest.raises(MoodleError, match="Invalid pagination cursor"):
        offset_of(cursor)


def test_offset_continuations_are_accepted() -> None:
    assert offset_of(None) == 0
    assert offset_of("20") == 20


def test_page_range_beyond_document_explains_the_problem() -> None:
    content = Extracted(pages=[TextPage(number=1, text="Lecture notes")])
    with pytest.raises(MoodleError, match="outside.*1 page"):
        excerpt(content, None, 500, 2, 3)

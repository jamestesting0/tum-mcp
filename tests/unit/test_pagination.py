import pytest

from tum_moodle.errors import MoodleError
from tum_moodle.models import Extracted, TextPage
from tum_moodle.pagination import excerpt


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

import pytest

from tum_moodle.errors import MoodleError
from tum_moodle.forums import posts_from_api
from tum_moodle.models import Material


def test_structured_forum_posts_keep_reply_relationships() -> None:
    discussion = Material(id="discussion:8", course_id=7, title="Timing", kind="discussion", url="")
    posts = posts_from_api(
        {
            "courseid": 7,
            "posts": [
                {
                    "id": 10,
                    "message": "<p>Deadline</p><script>bad()</script>",
                    "author": {"fullname": "Lecturer"},
                    "parentid": 9,
                    "timecreated": 42,
                }
            ],
        },
        discussion,
    )
    assert posts[0].text == "Deadline"
    assert posts[0].parent_id == "9"
    assert posts[0].author == "Lecturer"
    assert posts[0].url.endswith("?d=8#p10")


def test_cross_course_post_response_is_rejected() -> None:
    discussion = Material(id="discussion:8", course_id=7, title="", kind="discussion", url="")
    with pytest.raises(MoodleError, match="ACCESS_DENIED"):
        posts_from_api({"courseid": 9, "posts": []}, discussion)

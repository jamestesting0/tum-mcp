import pytest

from tum_moodle.errors import MoodleError
from tum_moodle.http_client import safe_url


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/pluginfile.php/1",
        "http://www.moodle.tum.de/course/view.php?id=1",
        "https://www.moodle.tum.de@evil.example/",
        "https://www.moodle.tum.de:444/",
        "/login/logout.php?sesskey=secret",
        "/mod/forum/view.php?id=1&action=subscribe",
        "https://127.0.0.1/",
    ],
)
def test_rejects_unsafe_or_mutating_urls(url: str) -> None:
    with pytest.raises(MoodleError):
        safe_url(url)


def test_resolves_content_links_without_fragments() -> None:
    assert safe_url("/mod/forum/discuss.php?d=12#p34") == (
        "https://www.moodle.tum.de/mod/forum/discuss.php?d=12"
    )

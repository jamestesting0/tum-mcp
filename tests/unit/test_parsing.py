from datetime import date

from tum_moodle.course_scope import current_term, select_courses
from tum_moodle.models import Course, Material
from tum_moodle.parsing import discussions_from_html, materials_from_html


def test_semester_labels_override_stale_in_progress_dates() -> None:
    courses = [
        Course(id=1, fullname="Old", shortname="Old (W25/26)", enddate=0),
        Course(id=2, fullname="Real Time", shortname="RTS (W26/27)"),
        Course(id=3, fullname="Advising", enddate=0),
    ]
    selected, ambiguous = select_courses(courses, date(2026, 10, 20))
    assert [course.id for course in selected] == [2]
    assert [course.id for course in ambiguous] == [3]
    assert current_term(date(2027, 2, 1)) == "W26/27"
    assert current_term(date(2027, 5, 1)) == "S27"


def test_course_parser_preserves_module_identity() -> None:
    html = """<li class="section"><h3 class="sectionname">Week 1</h3>
    <li class="activity"><a href="/mod/resource/view.php?id=42">
    <span class="instancename">Lecture<span class="accesshide"> File</span></span></a></li></li>"""
    result = materials_from_html(html, 7)
    assert len(result) == 1
    assert result[0].id == "module:42"
    assert result[0].title == "Lecture"
    assert result[0].section == "Week 1"


def test_repeated_discussion_links_do_not_replace_the_title() -> None:
    forum = Material(id="module:5", course_id=7, title="Forum", kind="forum", url="")
    discussions = discussions_from_html(
        '<a href="/mod/forum/discuss.php?d=8">Timing</a>'
        '<a href="/mod/forum/discuss.php?d=8&parent=10">20 Oct</a>',
        forum,
    )
    assert discussions[0].title == "Timing"
    assert discussions[0].url.endswith("?d=8")

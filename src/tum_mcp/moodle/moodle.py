from functools import cached_property
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from tum_mcp.moodle.course_scope import current_term, select_courses, term_of
from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.http_client import Download, MoodleHTTP
from tum_mcp.moodle.models import Course, CoursePage, Material
from tum_mcp.moodle.parsing import materials_from_html


class Moodle:
    def __init__(self, http: MoodleHTTP) -> None:
        self.http = http

    @cached_property
    def _snapshot(self) -> tuple[str, list[Course], list[Course]]:
        courses: dict[int, Course] = {}
        offset = 0
        for _ in range(100):
            result = self.http.read_api(
                "core_course_get_enrolled_courses_by_timeline_classification",
                {
                    "classification": "allincludinghidden",
                    "limit": 100,
                    "offset": offset,
                    "sort": "fullname",
                },
            )
            page = CoursePage.model_validate(result)
            courses.update({course.id: course for course in page.courses})
            if not page.courses or page.nextoffset <= offset:
                break
            offset = page.nextoffset
        else:
            raise MoodleError(ErrorCode.TOO_LARGE, "Course list exceeded the pagination limit.")
        preferred, ambiguous = select_courses(list(courses.values()))
        return current_term(), preferred, ambiguous

    def courses(self, include_past: bool = False) -> tuple[str, list[Course], list[Course]]:
        term, courses, unclassified = self._snapshot
        selected = (
            courses if include_past else [course for course in courses if term_of(course) == term]
        )
        return term, selected, unclassified

    def require_course(self, course_id: int) -> Download:
        """Verify current Moodle access, including courses absent from enrollment discovery."""
        page = self.http.get(f"/course/view.php?id={course_id}")
        location = urlsplit(page.url)
        soup = BeautifulSoup(page.text(), "html.parser")
        # Moodle can return enrollment/error HTML with HTTP 200; it is not course access.
        if (
            location.path != "/course/view.php"
            or parse_qs(location.query).get("id") != [str(course_id)]
            or soup.select_one(f"body.course-{course_id} .course-content") is None
        ):
            raise MoodleError(ErrorCode.ACCESS_DENIED, "This Moodle course is not accessible.")
        return page

    def materials(self, course_id: int) -> list[Material]:
        page = self.require_course(course_id)
        return materials_from_html(page.text(), course_id)

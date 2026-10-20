from functools import cached_property

from tum_moodle.course_scope import current_term, select_courses
from tum_moodle.errors import ErrorCode, MoodleError
from tum_moodle.http_client import MoodleHTTP
from tum_moodle.models import Course, CoursePage, Material
from tum_moodle.parsing import materials_from_html


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
                {"classification": "all", "limit": 100, "offset": offset, "sort": "fullname"},
            )
            page = CoursePage.model_validate(result)
            courses.update({course.id: course for course in page.courses})
            if not page.courses or page.nextoffset <= offset:
                break
            offset = page.nextoffset
        else:
            raise MoodleError(ErrorCode.TOO_LARGE, "Course list exceeded the pagination limit.")
        current, ambiguous = select_courses(list(courses.values()))
        return current_term(), current, ambiguous

    def courses(self) -> tuple[str, list[Course], list[Course]]:
        return self._snapshot

    def require_course(self, course_id: int) -> Course:
        _, courses, _ = self.courses()
        for course in courses:
            if course.id == course_id:
                return course
        raise MoodleError(ErrorCode.ACCESS_DENIED, "Select a current-semester enrolled course.")

    def materials(self, course_id: int) -> list[Material]:
        self.require_course(course_id)
        page = self.http.get(f"/course/view.php?id={course_id}")
        return materials_from_html(page.text(), course_id)

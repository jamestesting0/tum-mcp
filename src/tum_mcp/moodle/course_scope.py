import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tum_mcp.moodle.models import Course


def current_term(today: date | None = None) -> str:
    today = today or datetime.now(ZoneInfo("Europe/Berlin")).date()
    year = today.year % 100
    if today.month >= 10:
        return f"W{year:02}/{year + 1:02}"
    if today.month < 4:
        return f"W{year - 1:02}/{year:02}"
    return f"S{year:02}"


def term_of(course: Course) -> str | None:
    text = f"{course.shortname} {course.fullname}"
    winter = re.search(
        r"(?:W(?:S|iSe)?|Wintersemester)\s*(20)?(\d{2})\s*/\s*(?:20)?(\d{2})", text, re.I
    )
    if winter:
        return f"W{winter[2]}/{winter[3]}"
    summer = re.search(r"(?:\bS(?:S|oSe)?|Sommersemester)\s*(?:20)?(\d{2})\b", text, re.I)
    return f"S{summer[1]}" if summer else None


def select_courses(
    courses: list[Course], today: date | None = None
) -> tuple[list[Course], list[Course]]:
    term = current_term(today)
    return (
        [course for course in courses if term_of(course) == term],
        [course for course in courses if term_of(course) is None],
    )

"""When each source is taught, so "this week" resolves by code rather than by rereading.

sync-course writes `.tum-mcp/schedule.json` from the course page or TUMonline; without a
dated session it uses the material's release date and labels it as a proxy.
"""

import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, ValidationError

from tum_mcp.course.content.study import Label
from tum_mcp.course.project.models import Key, StudyState
from tum_mcp.course.project.store import confined, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


class Session(Frozen):
    on: datetime.date
    sources: tuple[Key, ...] = Field(min_length=1, max_length=20)
    label: Label | None = None
    # Where the date comes from; a release date only approximates when it was taught.
    basis: Literal["course page", "tumonline", "release"]


class Schedule(Frozen):
    sessions: tuple[Session, ...] = Field(max_length=400)


def read_schedule(root: Path, state: StudyState) -> Schedule | None:
    body = read_bytes(confined(root, ".tum-mcp/schedule.json"))
    if body is None:
        return None
    try:
        schedule = Schedule.model_validate_json(body)
    except ValidationError as error:
        raise CampusError(Code.INVALID_RESPONSE, f"Schedule: {error.errors()[0]['msg']}") from None
    known = {item.resource.key for item in state.resources}
    if unknown := sorted({k for s in schedule.sessions for k in s.sources} - known):
        raise CampusError(
            Code.INVALID_RESPONSE, f"Schedule names unknown sources: {', '.join(unknown)}"
        )
    return schedule


def week_of(schedule: Schedule, today: datetime.date) -> dict[str, JsonValue]:
    """The sessions of today's ISO week, what has been taught so far and what comes next."""
    week = today.isocalendar()[:2]
    ordered = sorted(schedule.sessions, key=lambda session: session.on)

    def row(session: Session) -> dict[str, JsonValue]:
        return session.model_dump(mode="json", exclude_none=True)

    upcoming = next((session for session in ordered if session.on > today), None)
    return {
        "today": today.isoformat(),
        "this_week": [row(s) for s in ordered if s.on.isocalendar()[:2] == week],
        "taught": sorted({key for s in ordered if s.on <= today for key in s.sources}),
        "next": row(upcoming) if upcoming else None,
        "proxy_dates": sorted({key for s in ordered if s.basis == "release" for key in s.sources}),
    }

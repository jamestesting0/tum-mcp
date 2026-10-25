"""Campus MCP surface; the existing Moodle tools remain compatibility aliases."""

import time
from typing import Annotated, Literal, assert_never

from mcp.types import ToolAnnotations
from pydantic import Field

from tum_mcp.artemis import Artemis
from tum_mcp.artemis.lecture_models import AttachmentView, LectureDirectory, LectureView
from tum_mcp.artemis.models import CourseDirectory, ExerciseView, FeedbackView, Overview
from tum_mcp.checkpoints import Checkpoint
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.server import server
from tum_mcp.settings import (
    Account,
    CourseMapping,
    Frozen,
    Preferences,
    Provider,
    find_account,
    preferences,
)
from tum_mcp.transport import API
from tum_mcp.zulip import Zulip
from tum_mcp.zulip.models import Channels, MessagePage, Query, Topics

READ = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=True)
Id = Annotated[int, Field(gt=0)]


class Status(Frozen):
    accounts: tuple["AccountStatus", ...]
    remote_action_status: str = "read_only"
    fetched_at: float


class AccountStatus(Frozen):
    account_id: str
    configuration: Account


class CapabilityStatus(Frozen):
    account_id: str
    instance_id: str
    provider: Provider
    identity_verified: bool
    version: str | None = None
    feature_level: int | None = None
    remote_actions_enabled: bool = False
    git_verified: bool = False


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def tum_status() -> Status:
    """Show configured account scopes without loading secrets or making network calls."""
    return Status(
        accounts=tuple(
            AccountStatus(account_id=a.id, configuration=a) for a in preferences().accounts
        ),
        fetched_at=time.time(),
    )


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def tum_get_preferences() -> Preferences:
    """Read user preferences. Permissions can only be changed through the local CLI."""
    return preferences()


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def tum_connect() -> str:
    """Return the trusted local connection command; never accept keys through chat."""
    return "Run tum-mcp connect in your terminal, select services and complete browser sign-in."


@server.tool(annotations=READ)
def tum_capabilities(account_id: str, provider: Provider) -> CapabilityStatus:
    """Verify provider identity and report independent, enabled read capabilities."""
    api = API(find_account(account_id, provider))
    match provider:
        case Provider.ZULIP:
            zulip = Zulip(api)
            zulip.identity()
            settings = zulip.settings()
            return CapabilityStatus(
                account_id=account_id,
                instance_id=api.account.origin,
                provider=provider,
                identity_verified=True,
                version=settings.zulip_version,
                feature_level=settings.zulip_feature_level,
            )
        case Provider.ARTEMIS:
            Artemis(api).identity()
            return CapabilityStatus(
                account_id=account_id,
                instance_id=api.account.origin,
                provider=provider,
                identity_verified=True,
            )
        case unreachable:
            assert_never(unreachable)


@server.tool(annotations=READ)
def zulip_list_channels(account_id: str, cursor: str | None = None) -> Channels:
    """Discover channel metadata; discovery does not grant message access."""
    return Zulip(API(find_account(account_id, Provider.ZULIP))).channel_page(cursor)


@server.tool(annotations=READ)
def zulip_list_topics(account_id: str, channel_id: Id, cursor: str | None = None) -> Topics:
    """List topics in one locally enabled, server-readable channel."""
    return Zulip(API(find_account(account_id, Provider.ZULIP))).topics(channel_id, cursor)


@server.tool(annotations=READ)
def zulip_search_messages(account_id: str, search: Query) -> MessagePage:
    """Search one enabled channel, with query-bound pagination and honest coverage."""
    return Zulip(API(find_account(account_id, Provider.ZULIP))).messages(search)


@server.tool(annotations=READ)
def zulip_read_topic(
    account_id: str, channel_id: Id, topic: str, cursor: str | None = None
) -> MessagePage:
    """Read a bounded topic page without changing unread state."""
    return Zulip(API(find_account(account_id, Provider.ZULIP))).messages(
        Query(channel_id=channel_id, topic=topic, cursor=cursor)
    )


@server.tool(annotations=READ)
def zulip_get_message(account_id: str, channel_id: Id, message_id: Id) -> MessagePage:
    """Re-fetch a cited message, checking current channel scope before returning it."""
    return Zulip(API(find_account(account_id, Provider.ZULIP))).messages(
        Query(channel_id=channel_id), message_id=message_id
    )


@server.tool(annotations=READ)
def zulip_get_checkpoint(account_id: str, channel_id: Id) -> Checkpoint | None:
    """Read the integration's catch-up checkpoint after rechecking current channel access."""
    from tum_mcp.checkpoints import get_checkpoint

    return get_checkpoint(Zulip(API(find_account(account_id, Provider.ZULIP))), channel_id)


@server.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
)
def zulip_save_checkpoint(account_id: str, channel_id: Id, message_id: Id) -> Checkpoint:
    """Advance a local summary checkpoint to an accessible message; does not mark it read."""
    from tum_mcp.checkpoints import save_checkpoint

    return save_checkpoint(
        Zulip(API(find_account(account_id, Provider.ZULIP))), channel_id, message_id
    )


@server.tool(annotations=READ)
def artemis_list_courses(account_id: str) -> CourseDirectory:
    """List available Artemis course metadata; this does not grant content access."""
    courses = Artemis(API(find_account(account_id, Provider.ARTEMIS))).courses()
    return CourseDirectory(account_id=account_id, courses=courses.root)


@server.tool(annotations=READ)
def artemis_list_exercises(account_id: str, course_id: Id) -> Overview:
    """List released course exercise metadata; excludes exams, quizzes and unreleased work."""
    return Artemis(API(find_account(account_id, Provider.ARTEMIS))).exercises(course_id)


@server.tool(annotations=READ)
def artemis_list_lectures(account_id: str, course_id: Id) -> LectureDirectory:
    """List student-visible lecture metadata in an enabled course, including tutorials."""
    from tum_mcp.artemis.lectures import Lectures

    return Lectures(Artemis(API(find_account(account_id, Provider.ARTEMIS)))).directory(course_id)


@server.tool(annotations=READ)
def artemis_get_lecture(account_id: str, course_id: Id, lecture_id: Id) -> LectureView:
    """Read released lecture text, slide metadata, video/online links and exercise references."""
    from tum_mcp.artemis.lectures import Lectures

    return Lectures(Artemis(API(find_account(account_id, Provider.ARTEMIS)))).lecture(
        course_id, lecture_id
    )


@server.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)
)
def artemis_get_attachment(
    account_id: str,
    course_id: Id,
    lecture_id: Id,
    attachment_id: Id,
    page_start: Id = 1,
    page_limit: Annotated[int, Field(ge=1, le=12)] = 8,
    save_original: bool = False,
) -> AttachmentView:
    """Read cited pages from the student PDF; optionally save that student copy locally."""
    from tum_mcp.artemis.lectures import Lectures

    return Lectures(Artemis(API(find_account(account_id, Provider.ARTEMIS)))).attachment(
        course_id,
        lecture_id,
        attachment_id,
        page_start=page_start,
        page_limit=page_limit,
        save_original=save_original,
    )


@server.tool(annotations=READ)
def artemis_get_exercise(account_id: str, course_id: Id, exercise_id: Id) -> ExerciseView:
    """Read a released statement without personal submission history; never starts it."""
    view = Artemis(API(find_account(account_id, Provider.ARTEMIS))).exercise(course_id, exercise_id)
    return view.model_copy(
        update={"exercise": view.exercise.model_copy(update={"student_participations": None})}
    )


@server.tool(annotations=READ)
def artemis_get_feedback(
    account_id: str,
    course_id: Id,
    exercise_id: Id,
    commit: str,
    mode: Literal["graded", "practice"] = "graded",
) -> FeedbackView:
    """Fetch only visible feedback linked to the exact built commit and participation mode."""
    provider = Artemis(API(find_account(account_id, Provider.ARTEMIS)))
    return provider.feedback(provider.exercise(course_id, exercise_id).exercise, mode, commit)


@server.tool(
    annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)
)
def tum_logout(account_id: str, provider: Provider) -> str:
    """Remove this account's local credential; remote API keys/sessions are not revoked."""
    from tum_mcp.credentials import Vault

    Vault().logout(find_account(account_id, provider))
    return "Local credential removed. Downloads and workspaces were preserved."


@server.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def tum_resolve_course(name: str) -> CourseMapping:
    """Resolve an explicitly configured course nickname; ambiguous names fail closed."""
    matches = [item for item in preferences().mappings if item.name.casefold() == name.casefold()]
    if len(matches) != 1:
        raise CampusError(
            Code.ACTION_REQUIRED, "Configure one exact course mapping in preferences.json."
        )
    return matches[0]

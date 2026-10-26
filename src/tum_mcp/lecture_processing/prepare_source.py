"""Course binding, canonical selected URLs and credential-free source identity."""

import hashlib
import json
import re
from pathlib import Path

from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing.captions import webvtt
from tum_mcp.lecture_processing.media_models import Manifest
from tum_mcp.lecture_processing.transcript_models import Passage
from tum_mcp.lecture_processing.validity import RecordingTiming, Validity, evaluate, require_content
from tum_mcp.settings import Provider, find_account, preferences
from tum_mcp.study_models import Binding
from tum_mcp.study_store import load_state
from tum_mcp.transport import API
from tum_mcp.tum_live.client import TumLive
from tum_mcp.tum_live.wire import Watch


def select(root: Path, url: str) -> tuple[Binding, str, int]:
    state = load_state(root)
    match = re.fullmatch(
        r"https://live\.rbg\.tum\.de/w/([A-Za-z0-9_-]{1,100})/([1-9][0-9]{0,15})/?", url
    )
    if match is None:
        raise CampusError(
            Code.SCOPE_DENIED,
            "Use a canonical TUM-Live recording URL without credentials or query parameters.",
        )
    slug, recording_id = match[1], int(match[2])
    bindings = [
        binding
        for binding in state.course.bindings
        if binding.provider == "tum_live" and binding.course_slug == slug
    ]
    if len(bindings) != 1:
        raise CampusError(
            Code.ACTION_REQUIRED,
            "Use sync-course to add this verified TUM-Live course binding to the project first.",
        )
    return bindings[0], slug, recording_id


def provider(binding: Binding) -> TumLive:
    account_id = binding.account_id
    if account_id is None:
        accounts = [
            account for account in preferences().accounts if account.provider == Provider.TUM_LIVE
        ]
        if len(accounts) != 1:
            raise CampusError(
                Code.AUTH_REQUIRED, "Select the connected TUM-Live account in this course binding."
            )
        account_id = accounts[0].id
    return TumLive(API(find_account(account_id, Provider.TUM_LIVE)))


def validity(watch: Watch, duration: float | None = None) -> Validity:
    return evaluate(
        RecordingTiming(
            duration_s=duration if duration is not None else watch.stream.duration,
            silences=watch.silences,
            start_offset_s=watch.start_offset,
            end_offset_s=watch.end_offset,
        )
    )


def revision(watch: Watch, valid: Validity, manifest: Manifest | None) -> str:
    fields = [
        watch.course.id,
        watch.course.slug,
        watch.stream.id,
        watch.stream.start.isoformat(),
        valid.model_dump(),
        manifest.revision if manifest else None,
    ]
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def missing(
    eligible: tuple[Interval, ...], processed: tuple[Interval, ...]
) -> tuple[Interval, ...]:
    result: list[Interval] = []
    for span in eligible:
        cursor = span.start_s
        for part in processed:
            if part.end_s <= cursor or part.start_s >= span.end_s:
                continue
            if cursor < part.start_s:
                result.append(Interval(start_s=cursor, end_s=min(part.start_s, span.end_s)))
            cursor = max(cursor, min(part.end_s, span.end_s))
        if cursor < span.end_s:
            result.append(Interval(start_s=cursor, end_s=span.end_s))
    return tuple(result)


def read_captions(
    service: TumLive, watch: Watch, valid: Validity, imported: Path | None, language: str
) -> tuple[Passage, ...]:
    require_content(valid)
    if imported is not None:
        if not imported.is_file() or imported.stat().st_size > 10 * 1024**2:
            raise CampusError(
                Code.INVALID_RESPONSE, "Imported WebVTT is missing or exceeds 10 MiB."
            )
        return webvtt(imported.read_bytes(), valid)
    available = watch.subtitle_languages
    selected = language if language in available else available[0] if available else ""
    if not selected:
        return ()
    if re.fullmatch(r"[A-Za-z0-9_-]{1,30}", selected) is None:
        raise CampusError(Code.INVALID_RESPONSE, "Provider caption language is malformed.")
    return webvtt(
        service.api.get(
            f"/api/v2/streams/{watch.course.slug}/{watch.stream.id}/subtitles/{selected}"
        ),
        valid,
    )

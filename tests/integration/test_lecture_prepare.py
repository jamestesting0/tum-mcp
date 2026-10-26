import io
import json
import shutil
import subprocess
import wave
from pathlib import Path

import httpx2
import pytest
from filelock import FileLock
from PIL import Image
from typer.testing import CliRunner

from tum_mcp.cli import app
from tum_mcp.credentials import Credential
from tum_mcp.lecture_evidence import Interval
from tum_mcp.lecture_processing import preparation, runtime
from tum_mcp.lecture_processing.media_http import MediaHTTP
from tum_mcp.lecture_processing.receipts import evidence_bytes
from tum_mcp.lecture_processing.transcript_models import AudioQuality, Recognition
from tum_mcp.moodle.auth import Cookie
from tum_mcp.settings import TUM_LIVE, Account, Provider
from tum_mcp.study_models import Binding, Course, Coverage, Resource, Snapshot
from tum_mcp.study_store import load_state
from tum_mcp.study_sync import sync
from tum_mcp.transport import API
from tum_mcp.tum_live.client import TumLive


@pytest.fixture
def lecture_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lecture_extension: Path):
    root = tmp_path / "course"
    root.mkdir()
    account = Account(provider=Provider.TUM_LIVE, origin=TUM_LIVE, principal="7")
    snapshot = Snapshot(
        schema_version=2,
        course=Course(
            key="course",
            title="Selected course",
            semester="winter",
            bindings=(
                Binding(
                    key="live",
                    provider="tum_live",
                    course_id="2464",
                    course_slug="950943622",
                    account_id=account.id,
                ),
            ),
        ),
        coverage=(Coverage(binding="live", status="partial", checked_at="fixture"),),
        resources=(
            Resource(
                key="unrelated",
                binding="live",
                kind="content",
                title="Unrelated source",
                url="https://example.invalid/material",
                text="Keep original",
            ),
        ),
    )
    path = tmp_path / "snapshot.json"
    path.write_text(snapshot.model_dump_json())
    sync(root, path, course_input="Selected course")
    stream = {
        "id": 11,
        "courseId": 2464,
        "start": "2026-10-14T10:00:00Z",
        "recording": True,
        "duration": None,
        "name": "Synthetic lecture",
    }
    course = {"id": 2464, "slug": "950943622", "name": "Selected course", "streams": [stream]}
    watch = {
        "course": course,
        "stream": stream,
        "silences": [],
        "subtitleLanguages": ["en"],
        "views": [
            {
                "kind": "WATCH_VIEW_KIND_PRESENTATION",
                "playlistUrl": "https://media.example.invalid/vod.m3u8?jwt=synthetic-secret",
            }
        ],
    }
    visited = []

    def service_response(request: httpx2.Request) -> httpx2.Response:
        visited.append(request.url.path)
        assert request.headers.get("cookie") == "session=synthetic-session"
        if request.url.path.endswith("users/me"):
            return httpx2.Response(200, json={"user": {"id": 7}})
        if request.url.path.endswith("courses/950943622"):
            return httpx2.Response(200, json={"course": course})
        if request.url.path.endswith("/watch"):
            return httpx2.Response(200, json=watch)
        if "/subtitles/" in request.url.path:
            return httpx2.Response(
                200,
                content=(
                    b"WEBVTT\n\n00:00.000 --> 00:05.000\nA classical bit is zero or one.\n"
                    b"\n00:05.000 --> 00:10.000\nThe amplitudes satisfy normalization.\n"
                ),
            )
        if request.url.path == "/api/v2/streams/11/files/15":
            output = io.BytesIO()
            with Image.new("RGB", (160, 90), "white") as image:
                image.save(output, format="PNG")
            return httpx2.Response(200, content=output.getvalue())
        raise AssertionError(request.url.path)

    credential = Credential(
        account_id=account.id,
        authentication="browser_session",
        cookies=(Cookie(name="session", value="synthetic-session", domain="live.rbg.tum.de"),),
    )
    service = TumLive(API(account, credential, httpx2.MockTransport(service_response)))
    monkeypatch.setattr(preparation, "provider", lambda _: service)

    def media_response(request: httpx2.Request) -> httpx2.Response:
        visited.append(request.url.path)
        assert "cookie" not in request.headers and "authorization" not in request.headers
        if request.url.path.endswith(".m3u8"):
            return httpx2.Response(
                200,
                content=b"#EXTM3U\n#EXT-X-TARGETDURATION:10\n#EXT-X-MEDIA-SEQUENCE:0\n#EXTINF:10,\nsegment.ts\n#EXT-X-ENDLIST\n",
            )
        raise AssertionError("Content acquisition was not expected")

    monkeypatch.setattr(
        preparation,
        "MediaHTTP",
        lambda grant, budget: MediaHTTP(grant, budget, httpx2.MockTransport(media_response)),
    )
    monkeypatch.setattr(
        runtime,
        "status",
        lambda: runtime.RuntimeStatus(
            supported=False,
            installed=False,
            ffmpeg=False,
            profile="fixture",
            reason="automatic_asr_unavailable",
        ),
    )
    return root, watch, visited


def invoke(*args: str):
    result = CliRunner().invoke(app, ["lecture", *args])
    assert result.exit_code == 0, result.output or repr(result.exception)
    return result


def test_cli_captions_export_sync_and_bounded_offline_reads_preserve_other_sources(
    lecture_project, tmp_path: Path
) -> None:
    root, watch, visited = lecture_project
    result = invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    assert "synthetic-secret" not in result.output
    receipt = json.loads(result.output)
    assert receipt["status"] == "prepared" and receipt["processed"] == [{"start_s": 0, "end_s": 10}]
    snapshot = tmp_path / "lectures.json"
    invoke("export-snapshot", str(root), "--output", str(snapshot))
    assert "classical bit" not in snapshot.read_text()
    sync(root, snapshot)
    assert {item.resource.key: item.status for item in load_state(root).resources} == {
        "live-2464-11": "current",
        "unrelated": "current",
    }
    before = list(visited)
    text = invoke("transcript", str(root), "--recording", "live-2464-11", "--limit", "1")
    assert len(json.loads(text.output)["passages"]) == 1 and "offline_cached" in text.output
    invoke("frames", str(root), "--recording", "live-2464-11")
    assert visited == before


def test_unknown_duration_whole_silence_stops_after_playlist_and_blocks_old_cache(
    lecture_project,
) -> None:
    root, watch, visited = lecture_project
    invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    original = evidence_bytes(root, "live-2464-11", "transcript.json")
    watch["silences"] = [{"start": 0, "end": 10}]
    visited.clear()
    result = invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    assert json.loads(result.output)["status"] == "invalid"
    assert visited[-1] == "/vod.m3u8" and not any("subtitles" in path for path in visited)
    assert (root / ".tum-mcp/lectures/live-2464-11/transcript.json").read_bytes() == original
    read = CliRunner().invoke(
        app, ["lecture", "transcript", str(root), "--recording", "live-2464-11"]
    )
    assert read.exit_code != 0 and "invalid" in str(read.exception).lower()


def test_known_whole_silence_never_opens_media_client(lecture_project) -> None:
    root, watch, visited = lecture_project
    watch["stream"]["duration"] = 10
    watch["silences"] = [{"start": 0, "end": 10}]
    result = invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    assert json.loads(result.output)["reason"] == "whole_recording_silence"
    assert not any(path.endswith(".m3u8") for path in visited)
    assert set(p.name for p in (root / ".tum-mcp/lectures/live-2464-11").iterdir()) == {
        "receipt.json",
        "prepare.lock",
    }


def test_wrong_course_and_concurrent_preparation_preserve_user_files(lecture_project) -> None:
    root, watch, visited = lecture_project
    custom = root / "notes.txt"
    custom.write_text("My authored explanation")
    wrong = CliRunner().invoke(
        app, ["lecture", "prepare", str(root), "--recording", "https://live.rbg.tum.de/w/other/11"]
    )
    assert wrong.exit_code != 0 and not visited
    directory = root / ".tum-mcp/lectures/live-2464-11"
    directory.mkdir(parents=True)
    with FileLock(str(directory / "prepare.lock")):
        concurrent = CliRunner().invoke(
            app,
            [
                "lecture",
                "prepare",
                str(root),
                "--recording",
                "https://live.rbg.tum.de/w/950943622/11",
            ],
        )
    assert concurrent.exit_code != 0 and "Another process" in str(concurrent.exception)
    assert custom.read_text() == "My authored explanation" and not visited


def test_missing_engine_reports_gap_without_download_or_false_success(lecture_project) -> None:
    root, watch, visited = lecture_project
    watch["subtitleLanguages"] = []
    result = invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    receipt = json.loads(result.output)
    assert receipt["status"] == "partial" and receipt["missing"] == [{"start_s": 0, "end_s": 10}]
    assert receipt["issues"] == ["automatic_asr_unavailable"]
    assert visited[-1] == "/vod.m3u8"


def test_corrupt_cached_transcript_cannot_be_read_as_valid_evidence(lecture_project) -> None:
    root, watch, visited = lecture_project
    invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    (root / ".tum-mcp/lectures/live-2464-11/transcript.json").write_text("[]")
    result = CliRunner().invoke(
        app, ["lecture", "transcript", str(root), "--recording", "live-2464-11"]
    )
    assert result.exit_code != 0 and "Cached lecture evidence changed" in str(result.exception)


def test_explicit_caption_import_is_reused_on_later_preparation(
    lecture_project, tmp_path: Path
) -> None:
    root, watch, visited = lecture_project
    watch["subtitleLanguages"] = []
    imported = tmp_path / "lecture.vtt"
    imported.write_text("WEBVTT\n\n00:00.000 --> 00:10.000\nSynthetic imported teaching.\n")
    first = invoke(
        "prepare",
        str(root),
        "--recording",
        "https://live.rbg.tum.de/w/950943622/11",
        "--transcript",
        str(imported),
    )
    imported.unlink()
    second = invoke("prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11")
    assert (
        json.loads(second.output)["source_revision"] == json.loads(first.output)["source_revision"]
    )
    assert json.loads(second.output)["status"] == "prepared"


def test_native_decode_cancel_resume_reuses_bytes_and_inference(
    lecture_project, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Optional local FFmpeg is unavailable")
    from tum_mcp.lecture_processing import chunk_store, preparation_audio
    from tum_mcp.lecture_processing.receipts import read_progress, recording_dir

    root, watch, visited = lecture_project
    vod = tmp_path / "vod"
    vod.mkdir()
    subprocess.run(  # noqa: S603 - fixed synthetic lavfi sources and owned temporary files
        [
            str(shutil.which("ffmpeg")),
            "-hide_banner",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=5:d=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=16000:duration=6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-g",
            "15",
            "-c:a",
            "aac",
            "-f",
            "hls",
            "-hls_time",
            "3",
            "-hls_list_size",
            "0",
            str(vod / "vod.m3u8"),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )  # noqa: S603
    watch["subtitleLanguages"] = []
    watch["endOffset"] = 5.7

    def media_response(request: httpx2.Request) -> httpx2.Response:
        body = (vod / request.url.path.lstrip("/")).read_bytes()
        if request.headers.get("if-none-match") == '"fixture-v1"':
            return httpx2.Response(304)
        return httpx2.Response(200, content=body, headers={"etag": '"fixture-v1"'})

    monkeypatch.setattr(
        preparation,
        "MediaHTTP",
        lambda grant, budget: MediaHTTP(grant, budget, httpx2.MockTransport(media_response)),
    )
    monkeypatch.setattr(
        runtime,
        "status",
        lambda: runtime.RuntimeStatus(
            supported=True, installed=True, ffmpeg=True, profile="injected-protocol", reason="ready"
        ),
    )
    # Native media/decode and real cache/CLI, with an explicitly injected recognition protocol.
    monkeypatch.setattr(preparation_audio, "sample_spans", lambda _: ())
    monkeypatch.setattr(
        preparation_audio,
        "chunks",
        lambda _: (Interval(start_s=0, end_s=3), Interval(start_s=3, end_s=5.7)),
    )

    def quality(path: Path) -> AudioQuality:
        with wave.open(str(path)) as audio:
            duration = audio.getnframes() / audio.getframerate()
        return AudioQuality.model_validate(
            {
                "duration_s": duration,
                "channels": [
                    {
                        "channel": 0,
                        "rms": 0.1,
                        "clipped_fraction": 0,
                        "windows": [{"start_s": 0, "end_s": duration, "speech_s": duration}],
                    }
                ],
            }
        )

    calls = []

    def recognize(*args, **kwargs) -> Recognition:
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return Recognition.model_validate(
            {
                "language": "en",
                "segments": [
                    {
                        "start": 1,
                        "end": 2,
                        "text": " Synthetic statement.",
                        "avg_logprob": -0.1,
                        "no_speech_prob": 0.1,
                        "compression_ratio": 1,
                        "words": [
                            {
                                "start": 1,
                                "end": 2,
                                "word": " Synthetic statement.",
                                "probability": 0.9,
                            }
                        ],
                    }
                ],
            }
        )

    monkeypatch.setattr(chunk_store, "analyze", quality)
    monkeypatch.setattr(chunk_store, "recognize", recognize)
    interrupted = CliRunner().invoke(
        app,
        [
            "lecture",
            "prepare",
            str(root),
            "--recording",
            "https://live.rbg.tum.de/w/950943622/11",
            "--language",
            "en",
        ],
    )
    assert interrupted.exit_code != 0
    progress = read_progress(recording_dir(root, "live-2464-11"))
    assert progress is not None and progress.processed == (Interval(start_s=0, end_s=3),)
    resumed = invoke(
        "prepare",
        str(root),
        "--recording",
        "https://live.rbg.tum.de/w/950943622/11",
        "--language",
        "en",
    )
    receipt = json.loads(resumed.output)
    assert receipt["status"] == "prepared" and receipt["chunks_reused"] == 1 and len(calls) == 3
    again = invoke(
        "prepare",
        str(root),
        "--recording",
        "https://live.rbg.tum.de/w/950943622/11",
        "--language",
        "en",
    )
    final = json.loads(again.output)
    assert final["chunks_reused"] == 2 and len(calls) == 3
    assert (
        final["bytes_downloaded"] < 1024 and final["source_revision"] == receipt["source_revision"]
    )
    compact = json.loads(invoke("transcript", str(root), "--recording", "live-2464-11").output)
    detailed = json.loads(
        invoke("transcript", str(root), "--recording", "live-2464-11", "--words").output
    )
    assert "words" not in compact["passages"][0] and detailed["passages"][0]["words"]
    assert compact["passages"][0]["interval"] == detailed["passages"][0]["interval"]
    invoke(
        "prepare",
        str(root),
        "--recording",
        "https://live.rbg.tum.de/w/950943622/11",
        "--language",
        "en",
        "--frame-at",
        "3.55",
    )
    with_frame = json.loads(evidence_bytes(root, "live-2464-11", "frames.json"))
    invoke(
        "prepare",
        str(root),
        "--recording",
        "https://live.rbg.tum.de/w/950943622/11",
        "--language",
        "en",
    )
    assert (
        json.loads(evidence_bytes(root, "live-2464-11", "frames.json"))["captured"]
        == with_frame["captured"]
    )
    assert len(with_frame["captured"]) == 1 and len(calls) == 3


@pytest.mark.parametrize("requested", [False, True])
def test_seek_previews_are_fetched_only_when_explicitly_requested(
    lecture_project, requested: bool
) -> None:
    root, watch, visited = lecture_project
    watch["views"][0]["sprite"] = {"fileId": 15, "intervalSeconds": 10}
    args = ["prepare", str(root), "--recording", "https://live.rbg.tum.de/w/950943622/11"]
    if requested:
        args.append("--previews")
    invoke(*args)
    frames = json.loads(evidence_bytes(root, "live-2464-11", "frames.json"))
    assert len(frames["candidates"]) == (1 if requested else 0)
    assert ("/api/v2/streams/11/files/15" in visited) is requested
    assert frames["captured"] == []


def test_explicit_visual_requests_cannot_bypass_whole_silence_gate(lecture_project) -> None:
    root, watch, visited = lecture_project
    watch["views"][0]["sprite"] = {"fileId": 15, "intervalSeconds": 10}
    watch["silences"] = [{"start": 0, "end": 10}]
    result = invoke(
        "prepare",
        str(root),
        "--recording",
        "https://live.rbg.tum.de/w/950943622/11",
        "--previews",
        "--frame-at",
        "0",
    )
    assert json.loads(result.output)["status"] == "invalid"
    assert not any(
        "/files/" in path or "subtitles" in path or path.endswith(".ts") for path in visited
    )

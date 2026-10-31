from pathlib import Path

import pytest
from keyring.backend import KeyringBackend

from tum_mcp.moodle import auth


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[service, username] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.values[service, username]


@pytest.fixture
def memory_keyring(monkeypatch: pytest.MonkeyPatch) -> KeyringBackend:
    backend = MemoryKeyring()
    monkeypatch.setattr(auth, "system_keyring", lambda: backend)
    return backend


@pytest.fixture
def lecture_extension(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Opt in explicitly for lecture scenarios; ordinary fixtures keep the base surface."""
    from tum_mcp.extensions import LectureInstallation

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "lecture-data"))
    folder = tmp_path / "lecture-data/config"
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(folder))
    folder.mkdir(parents=True)
    selected = LectureInstallation(
        enabled=True,
        installed_at="2026-10-26T10:00:00Z",
        package_version="fixture",
        asr_requested=False,
    )
    (folder / "lecture-extension.json").write_text(selected.model_dump_json())
    return folder


@pytest.fixture
def media_audio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One source-bound AAC codec fixture; it makes no actual speech-quality claim."""
    import hashlib
    import json

    from tum_mcp.audio_content import (
        AudioFile,
        AudioManifest,
        AudioReceipt,
        AudioUnit,
        AudioValidation,
        MediaFile,
        TeachingReviewFile,
        category_hash,
    )
    from tum_mcp.media_projection import guidance_hash
    from tum_mcp.study_build import read_content
    from tum_mcp.study_sync import sync
    from tum_mcp.video_content import Locator, locator_fingerprint, semantic_hash

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    fixtures = Path(__file__).parent / "fixtures"
    root = tmp_path / "media-course"
    snapshot = fixtures / "course_app/snapshot.json"
    sync(root, snapshot, course_input=json.loads(snapshot.read_bytes())["course"]["title"])
    (root / "app").mkdir(exist_ok=True)
    (root / "app/content.json").write_bytes((fixtures / "course_app/content.json").read_bytes())
    content = read_content(root)
    unit = next(u for u in content.units if u.key == "bfs")
    stem = "01_graph-revision"

    def artifact(relative: str, data: bytes) -> AudioFile:
        path = root / "audio" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return AudioFile(path=relative, sha256=hashlib.sha256(data).hexdigest(), size=len(data))

    def proof(file: AudioFile) -> MediaFile:
        return MediaFile(path=file.path, sha256=file.sha256)

    script = artifact(f"scripts/{stem}.txt", b"The queue retains the discovery order.\n")
    track = artifact(f"tracks/{stem}.m4a", (fixtures / "video/audio.m4a").read_bytes())
    chapter = artifact(
        f"chapters/{stem}.json",
        json.dumps([{"key": "queue", "title": "Queue order", "start": 0, "end": 2}]).encode(),
    )
    raw_probe = artifact(
        f".build/{stem}/probe.json", (fixtures / "video/audio-probe.json").read_bytes()
    )
    raw_signal = artifact(
        f".build/{stem}/signal.txt", (fixtures / "video/audio-signal.txt").read_bytes()
    )
    probe = json.loads((fixtures / "video/audio-probe.json").read_bytes())
    signal = (fixtures / "video/audio-signal.txt").read_text(encoding="utf-8")
    start = signal.index("{\n")
    loudness = json.loads(signal[start : signal.index("\n}", start) + 2])
    version = next(
        line.split()[-1] for line in signal.splitlines() if "encoder" in line and "Lavf" in line
    )
    measurements = AudioValidation(
        artifact_sha256=track.sha256,
        tool={"name": "ffmpeg/ffprobe", "version": version},
        duration=float(probe["format"]["duration"]),
        codec=probe["streams"][0]["codec_name"],
        container=probe["format"]["format_name"],
        sample_rate=int(probe["streams"][0]["sample_rate"]),
        channels=probe["streams"][0]["channels"],
        decoded=True,
        loudness_lufs=float(loudness["input_i"]),
        true_peak_dbtp=float(loudness["input_tp"]),
        probe=proof(raw_probe),
        decode=proof(raw_signal),
        loudness=proof(raw_signal),
    )
    validation = artifact(f".build/{stem}/validation.json", measurements.model_dump_json().encode())
    review = artifact(
        f".build/{stem}/teaching.md",
        b"Synthetic codec fixture, not a listening or teaching-quality receipt.\n",
    )
    units = (AudioUnit(unit=unit.key, semantic_sha256=semantic_hash(unit)),)
    locator = Locator(kind="summary", ref="summary", fingerprint="0" * 64)
    locator = locator.model_copy(update={"fingerprint": locator_fingerprint(unit, locator)})
    receipt = AudioReceipt(
        key="graphs",
        stem=stem,
        title="Graph revision",
        units=units,
        category_sha256=category_hash("Graph revision", units),
        source_references=unit.sources,
        script=script,
        track=track,
        chapters=chapter,
        voice={"provider": "synthetic", "route": "fixture", "voice": "tone", "language": "en"},
        chunk_inputs=[{"key": "queue", "sha256": script.sha256}],
        duration=2,
        coverage=[
            {
                "unit": "bfs",
                "locator": locator,
                "section": "queue",
                "chapter": "queue",
                "mode": "spoken",
            }
        ],
        teaching_review=TeachingReviewFile(
            path=review.path, sha256=review.sha256, guidance_sha256=guidance_hash("audio")
        ),
        validation=proof(validation),
    )
    manifest = AudioManifest(course_key=content.course_key, categories={"graphs": receipt})
    (root / "audio/manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return root

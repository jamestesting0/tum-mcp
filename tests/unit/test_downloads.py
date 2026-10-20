from pathlib import Path

import pytest

from tum_moodle.downloads import list_downloads, save_download
from tum_moodle.errors import MoodleError
from tum_moodle.http_client import Download
from tum_moodle.models import Material


def test_download_creates_a_real_local_file_with_safe_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TUM_MOODLE_DOWNLOAD_DIR", str(tmp_path))
    material = Material(
        id="module:1", course_id=7, title="../../Lecture 1", kind="resource", url=""
    )
    response = Download(
        "https://www.moodle.tum.de/file", "application/pdf", b"%PDF-local-file", "", ""
    )
    result = save_download(material, response)
    path = Path(result["path"])
    assert path.read_bytes() == b"%PDF-local-file"
    assert path.parent == tmp_path / "course-7"
    assert path.suffix == ".pdf"
    assert list_downloads()[0]["path"] == str(path)
    assert save_download(material, response) == result


def test_recordings_are_not_saved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TUM_MOODLE_DOWNLOAD_DIR", str(tmp_path))
    material = Material(id="module:1", course_id=7, title="Recording", kind="resource", url="")
    with pytest.raises(MoodleError, match="links only"):
        save_download(material, Download("", "video/mp4", b"", "", ""))
    assert list_downloads() == []


def test_mislabeled_html_is_not_saved_as_a_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MOODLE_DOWNLOAD_DIR", str(tmp_path))
    material = Material(id="module:1", course_id=7, title="Lecture", kind="resource", url="")
    with pytest.raises(MoodleError, match="not a PDF"):
        save_download(
            material, Download("/file.pdf", "application/pdf", b"<html>login</html>", "", "")
        )
    assert list_downloads() == []

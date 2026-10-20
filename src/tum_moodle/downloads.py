import hashlib
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pydantic import JsonValue

from tum_moodle.errors import ErrorCode, MoodleError
from tum_moodle.http_client import Download
from tum_moodle.models import Material


def downloads_root() -> Path:
    override = os.environ.get("TUM_MOODLE_DOWNLOAD_DIR")
    return Path(override) if override else Path.home() / "Downloads/TUM Moodle"


def save_download(material: Material, download: Download) -> dict[str, JsonValue]:
    if download.content_type.startswith(("video/", "audio/")):
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Recordings are links only.")
    suffix = Path(unquote(urlsplit(download.url).path)).suffix.lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):
        suffix = mimetypes.guess_extension(download.content_type) or ".bin"
    if download.body.startswith(b"%PDF-"):
        suffix = ".pdf"
    elif suffix == ".pdf":
        raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Server response is not a PDF file.")
    stem = re.sub(r"[^\w .()-]", "_", material.title).strip(" .")[:100] or "material"
    digest = hashlib.sha256(download.body).hexdigest()
    folder = downloads_root() / f"course-{material.course_id}"
    if folder.is_symlink() or downloads_root().is_symlink():
        raise MoodleError(ErrorCode.SETUP_REQUIRED, "The download folder must not be a symlink.")
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = folder / f"{stem}-{digest[:12]}{suffix}"
    try:
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise MoodleError(
                ErrorCode.SETUP_REQUIRED, "An unrelated file occupies this path."
            ) from None
    else:
        with os.fdopen(descriptor, "wb") as file:
            file.write(download.body)
    return {
        "path": str(target.resolve()),
        "filename": target.name,
        "bytes": len(download.body),
        "sha256": digest,
        "source": material.url,
        "retention": "Saved download; not removed by cache cleanup.",
    }


def list_downloads() -> list[dict[str, JsonValue]]:
    root = downloads_root()
    if not root.exists() or root.is_symlink():
        return []
    files: list[dict[str, JsonValue]] = []
    for folder in sorted(root.glob("course-*")):
        if folder.is_symlink() or not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.is_file() and not path.is_symlink():
                files.append(
                    {"path": str(path), "filename": path.name, "bytes": path.stat().st_size}
                )
    return files

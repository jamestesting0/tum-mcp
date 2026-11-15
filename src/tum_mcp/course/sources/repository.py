"""A local snapshot of an exercise's template repository: source files only, with digests."""

import fnmatch
import re
import shutil
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, Field

from tum_mcp.course.project.store import confined, digest, private_path
from tum_mcp.errors import CampusError, Code

SOURCE_SUFFIXES = frozenset(
    {
        ".java", ".kt", ".kts", ".scala", ".py", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs",
        ".js", ".ts", ".swift", ".go", ".rs", ".hs", ".ml", ".sql", ".r", ".m", ".jl",
        ".txt", ".csv", ".json", ".md",
    }
)  # fmt: skip
# Build scripts and wrappers can hold URLs or credentials and never teach the task.
BUILD_NAMES = frozenset(
    {
        "build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts",
        "gradlew", "gradlew.bat", "pom.xml", "mvnw", "mvnw.cmd", "makefile", "cmakelists.txt",
        "gradle.properties", "build.xml", "package.json", "package-lock.json",
    }
)  # fmt: skip
BUILD_FOLDERS = frozenset({"gradle", "build", "target", "out", "bin", "node_modules"})
KEY = re.compile(r"artemis-\d{1,12}")
MAX_FILES = 60
MAX_FILE_CHARS = 50_000
MAX_TOTAL_CHARS = 400_000


class Dropped(BaseModel):
    path: str
    reason: str


class Manifest(BaseModel):
    """What `study repository` read: the template commit and each kept file's digest."""

    key: str
    commit: str
    files: dict[str, str] = Field(description="Each kept path and the SHA-256 of its text.")
    dropped: tuple[Dropped, ...] = ()
    include: tuple[str, ...] = ()


def drop_reason(path: str, text: str) -> str | None:
    parts = PurePosixPath(path).parts
    name = parts[-1].casefold()
    if any(part.startswith(".") for part in parts):
        return "hidden file or folder (git, IDE or CI settings)"
    if name in BUILD_NAMES or any(part.casefold() in BUILD_FOLDERS for part in parts[:-1]):
        return "build script or build output"
    if PurePosixPath(name).suffix not in SOURCE_SUFFIXES:
        return "not a source or text file"
    if "\x00" in text:
        return "binary content"
    return None


def select(
    files: dict[str, str], include: tuple[str, ...] = ()
) -> tuple[dict[str, str], tuple[Dropped, ...]]:
    """The files a project shows, and every other path with why it stays out."""
    kept: dict[str, str] = {}
    dropped: list[Dropped] = []
    for path in sorted(files):
        reason = drop_reason(path, files[path])
        if reason is None and include and not any(fnmatch.fnmatch(path, glob) for glob in include):
            reason = "outside --include"
        if reason is None and len(files[path]) > MAX_FILE_CHARS:
            reason = f"longer than {MAX_FILE_CHARS:,} characters"
        if reason:
            dropped.append(Dropped(path=path, reason=reason))
        else:
            kept[path] = files[path]
    total = sum(len(text) for text in kept.values())
    if len(kept) > MAX_FILES or total > MAX_TOTAL_CHARS:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            f"The repository keeps {len(kept)} files and {total:,} characters, more than the "
            f"editor holds ({MAX_FILES} files, {MAX_TOTAL_CHARS:,} characters). Narrow it with "
            "--include GLOB.",
        )
    if not kept:
        raise CampusError(Code.INVALID_RESPONSE, "The repository has no source files to show.")
    return kept, tuple(dropped)


def folder(root: Path, key: str) -> Path:
    return private_path(root, f"repositories/{key}")


def write_snapshot(
    target: Path, key: str, commit: str, files: dict[str, str], include: tuple[str, ...] = ()
) -> Manifest:
    """Replace the snapshot in `target`: the kept files as real files beside a digest
    manifest."""
    kept, dropped = select(files, include)
    if target.exists():
        shutil.rmtree(target)
    for path, text in kept.items():
        destination = confined(target / "files", path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="")
    manifest = Manifest(
        key=key,
        commit=commit,
        files={path: digest(text.encode()) for path, text in kept.items()},
        dropped=dropped,
        include=include,
    )
    (target / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def read_snapshot(source: Path) -> tuple[Manifest, dict[str, str]]:
    """A snapshot's manifest and files, refused when a file no longer matches its digest."""
    path = source / "manifest.json"
    if not path.is_file():
        raise CampusError(
            Code.ACTION_REQUIRED,
            "No repository snapshot there; read it with artemis_get_repository.",
        )
    manifest = Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    for name, sha256 in manifest.files.items():
        text = confined(source / "files", name).read_text(encoding="utf-8")
        if digest(text.encode()) != sha256:
            raise CampusError(
                Code.WORKSPACE_CONFLICT,
                f"The snapshot copy of {name} changed; read the repository again.",
            )
        files[name] = text
    return manifest, files


def import_snapshot(root: Path, source: Path) -> tuple[Manifest, dict[str, str]]:
    """Copy a verified snapshot into the course project, where projects are checked against it."""
    manifest, files = read_snapshot(source)
    if not KEY.fullmatch(manifest.key):
        raise CampusError(Code.INVALID_RESPONSE, "The snapshot key is not an Artemis exercise key.")
    write_snapshot(
        folder(root, manifest.key), manifest.key, manifest.commit, files, manifest.include
    )
    return read_snapshot(folder(root, manifest.key))


def read_clone(folder: Path) -> dict[str, str]:
    """A repository folder the student holds, read without entering hidden folders such as
    `.git`, so credentials and remote URLs are never opened."""
    if not folder.is_dir():
        raise CampusError(Code.INVALID_RESPONSE, f"{folder} is not a folder.")
    files: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 4 * MAX_FILE_CHARS:
            continue
        try:
            files[relative.as_posix()] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            files[relative.as_posix()] = "\x00"
    return files


def import_clone(
    root: Path, clone: Path, exercise: int, include: tuple[str, ...] = ()
) -> tuple[Manifest, dict[str, str]]:
    """Snapshot a clone of the student's own repository as the exercise's template."""
    key, files = f"artemis-{exercise}", read_clone(clone)
    write_snapshot(folder(root, key), key, "clone", files, include)
    return read_snapshot(folder(root, key))


def project_snapshot(root: Path, key: str) -> tuple[Manifest, dict[str, str]] | None:
    """The project's snapshot for an exercise source, when it has one."""
    if not (folder(root, key) / "manifest.json").is_file():
        return None
    return read_snapshot(folder(root, key))


def listing(manifest: Manifest, files: dict[str, str]) -> dict[str, object]:
    """What the agent needs to plan the project, never the file text."""
    return {
        "key": manifest.key,
        "commit": manifest.commit,
        "files": [
            {
                "path": path,
                "chars": len(files[path]),
                "sha256": sha256,
                "todo": "TODO" in files[path],
            }
            for path, sha256 in manifest.files.items()
        ],
        "dropped": [item.model_dump() for item in manifest.dropped],
        "next_action": "Pack the project with tum-mcp study files PROJECT EXERCISE "
        f"--from {manifest.key} --editable PATH ... --solutions DIR.",
    }

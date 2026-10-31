"""Variants: a copy of the repo at a base plus patches, with its own Python environment."""

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from skill_lab import LabError, paths, safety

WORKTREE = "WORKTREE"


@dataclass
class Base:
    ref: str
    patches: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ref": self.ref, "patches": list(self.patches)}

    @classmethod
    def from_dict(cls, value: dict) -> "Base":
        return cls(str(value["ref"]), [str(item) for item in value.get("patches", [])])


def resolve_ref(ref: str) -> str:
    if ref == WORKTREE:
        return WORKTREE
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=paths.REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise LabError(f"Unknown git ref {ref!r}.")
    return result.stdout.strip()


def check_patch(patch: Path) -> list[str]:
    if not patch.is_file():
        raise LabError(f"Patch {patch} does not exist.")
    touched = safety.patch_paths(patch.read_text(encoding="utf-8"))
    if not touched:
        raise LabError(f"Patch {patch} changes no files.")
    outside = [path for path in touched if not path.startswith("src/tum_mcp/")]
    if outside:
        raise LabError("Variants may only change files under src/tum_mcp/: " + ", ".join(outside))
    blocked = safety.guarded(touched)
    if blocked:
        raise LabError(
            "Variants may not change campus, session, install or lab code: " + ", ".join(blocked)
        )
    return touched


def materialize(ref: str, destination: Path) -> None:
    destination.mkdir(parents=True)
    if ref == WORKTREE:
        listed = subprocess.run(
            ["git", "ls-files", "-z"], cwd=paths.REPO, capture_output=True, check=True
        ).stdout
        for relative in filter(None, listed.decode().split("\0")):
            source = paths.REPO / relative
            if source.is_file():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        return
    archive = subprocess.run(
        ["git", "archive", "--format=tar", ref], cwd=paths.REPO, capture_output=True, check=True
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(destination, filter="data")


def apply_patch(patch: Path, repo: Path) -> None:
    check_patch(patch)
    # The variant copy sits inside this repository's .omo/; without a ceiling, git would
    # treat it as a subdirectory of the outer repo and silently skip every path.
    environment = {**os.environ, "GIT_CEILING_DIRECTORIES": str(repo.parent)}
    for arguments in ([], ["--reverse", "--check"]):
        result = subprocess.run(
            ["git", "apply", "--whitespace=nowarn", *arguments, str(patch.resolve())],
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise LabError(f"Patch {patch.name} did not apply: {result.stderr.strip()[:400]}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def spec_of(base: Base, patch: Path | None) -> dict:
    chain = [*base.patches, *([str(patch.resolve())] if patch else [])]
    return {"ref": base.ref, "patches": [{"path": p, "sha256": digest(Path(p))} for p in chain]}


def python_of(variant_dir: Path) -> Path:
    return variant_dir / "venv" / "bin" / "python"


def create(round_id: str, name: str, base: Base, patch: Path | None = None) -> Path:
    directory = paths.round_dir(round_id) / "variants" / name
    wanted = spec_of(base, patch)
    record = directory / "variant.json"
    if record.is_file():
        existing = json.loads(record.read_text(encoding="utf-8"))
        if existing.get("spec") == wanted and python_of(directory).is_file():
            return directory
        raise LabError(f"Variant {name} already exists with a different base or patch.")
    if directory.exists():
        shutil.rmtree(directory)
    repo = directory / "repo"
    materialize(base.ref, repo)
    for entry in wanted["patches"]:
        apply_patch(Path(entry["path"]), repo)
    subprocess.run(
        ["uv", "venv", "--quiet", "--python", "3.13", str(directory / "venv")], check=True
    )
    subprocess.run(
        ["uv", "pip", "install", "--quiet", "--python", str(python_of(directory)), str(repo)],
        check=True,
    )
    record.write_text(json.dumps({"name": name, "spec": wanted}, indent=2), encoding="utf-8")
    return directory


def touched_paths(variant_dir: Path) -> list[str]:
    spec = json.loads((variant_dir / "variant.json").read_text(encoding="utf-8"))["spec"]
    found: set[str] = set()
    for entry in spec["patches"]:
        found.update(safety.patch_paths(Path(entry["path"]).read_text(encoding="utf-8")))
    return sorted(found)

"""Reuse the npm launcher's verified uv binary without mutating the base environment."""

import hashlib
import shutil
import sys

from pydantic import Field, ValidationError

from tum_mcp.settings import Frozen, data_dir


class UvOwner(Frozen):
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def installer_uv() -> str | None:
    root = data_dir()
    executable = root / ("uv.exe" if sys.platform == "win32" else "uv")
    receipt = root / "uv-owner.json"
    if (
        not executable.is_symlink()
        and not receipt.is_symlink()
        and executable.is_file()
        and executable.stat().st_size <= 128 * 1024**2
        and receipt.is_file()
        and receipt.stat().st_size <= 1024
    ):
        try:
            owner = UvOwner.model_validate_json(receipt.read_bytes())
            with executable.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == owner.sha256:
                    return str(executable)
        except (OSError, ValidationError):
            pass
    return shutil.which("uv")

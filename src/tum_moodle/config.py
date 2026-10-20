import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from tum_moodle.platforms import data_root

BASE_URL: Final = "https://www.moodle.tum.de"
MAX_BYTES: Final = 50 * 1024 * 1024
CACHE_BYTES: Final = 1024 * 1024 * 1024
CACHE_DAYS: Final = 30


@dataclass(frozen=True, slots=True)
class Paths:
    root: Path

    @classmethod
    def default(cls) -> "Paths":
        root = data_root()
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root.chmod(0o700)
        return cls(root.resolve())

    def file(self, name: str) -> Path:
        return self.root / name


def private_write(path: Path, content: bytes) -> None:
    """Atomically replace a private file, without a world-readable temporary copy."""
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

import os
import sys
from enum import Enum
from pathlib import Path


class System(Enum):
    MACOS = "darwin"
    WINDOWS = "win32"
    LINUX = "linux"


def system() -> System:
    return System(sys.platform)


def app_root() -> Path:
    home = Path.home()
    locations = {
        System.MACOS: home / "Library/Application Support",
        System.WINDOWS: Path(os.environ.get("LOCALAPPDATA") or home / "AppData/Local"),
        System.LINUX: Path(os.environ.get("XDG_DATA_HOME") or home / ".local/share"),
    }
    return locations[system()] / "TUMMoodle"


def data_root() -> Path:
    override = os.environ.get("TUM_MOODLE_DATA_DIR")
    return Path(override).expanduser() if override else app_root()


def runtime_python() -> Path:
    executable = "Scripts/python.exe" if system() is System.WINDOWS else "bin/python"
    return app_root() / "runtime" / executable

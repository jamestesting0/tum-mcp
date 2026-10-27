"""Local-file encryption keys, protected by owner permissions rather than a keychain."""

import os
import shutil
import stat
import subprocess
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from filelock import FileLock

from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.errors import ErrorCode, MoodleError


@lru_cache(maxsize=64)
def _secure_windows_path(path: Path) -> None:
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not powershell:
        raise MoodleError(ErrorCode.SETUP_REQUIRED, "Windows file protection requires PowerShell.")
    script = (
        "$ErrorActionPreference='Stop'; "
        "$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
        "$path=$env:TUM_MCP_PRIVATE_DIRECTORY; "
        "$directory=[System.IO.Directory]::Exists($path); "
        "$acl=if($directory){[System.Security.AccessControl.DirectorySecurity]::new()}"
        "else{[System.Security.AccessControl.FileSecurity]::new()}; "
        "$inherit=if($directory){'OICI'}else{''}; "
        "$sddl='D:P(A;'+$inherit+';FA;;;'+$sid+')'; "
        "$acl.SetSecurityDescriptorSddlForm($sddl, "
        "[System.Security.AccessControl.AccessControlSections]::Access); "
        "if($PSVersionTable.PSEdition -eq 'Core'){"
        "$item=if($directory){[System.IO.DirectoryInfo]::new($path)}"
        "else{[System.IO.FileInfo]::new($path)}; "
        "[System.IO.FileSystemAclExtensions]::SetAccessControl($item,$acl)"
        "}elseif($directory){[System.IO.Directory]::SetAccessControl($path,$acl)}"
        "else{[System.IO.File]::SetAccessControl($path,$acl)}"
    )
    try:
        subprocess.run(  # noqa: S603
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "TUM_MCP_PRIVATE_DIRECTORY": str(path)},
            capture_output=True,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        raise MoodleError(
            ErrorCode.SETUP_REQUIRED, "Could not restrict Windows credential permissions."
        ) from None


def secure_directory(path: Path) -> None:
    try:
        if path.is_symlink():
            raise MoodleError(ErrorCode.SETUP_REQUIRED, "Credential directory cannot be a symlink.")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "nt":
            _secure_windows_path(path.resolve())
        else:
            if path.stat().st_uid != os.getuid():
                raise MoodleError(
                    ErrorCode.SETUP_REQUIRED, "Credential directory belongs to another user."
                )
            path.chmod(0o700)
    except OSError:
        raise MoodleError(
            ErrorCode.SETUP_REQUIRED, "Cannot secure the local credential directory."
        ) from None


def local_cipher(root: Path, *, create: bool = False) -> Fernet:
    """Never reads native stores. A missing/corrupt key never silently replaces a saved key."""
    if not root.exists() and not create:
        raise MoodleError(ErrorCode.AUTH_REQUIRED, "Reconnect with tum-mcp login.")
    secure_directory(root)
    path = root / "session.key"
    with FileLock(str(root / "key.lock")):
        if path.is_symlink():
            raise MoodleError(ErrorCode.SETUP_REQUIRED, "Credential key cannot be a symlink.")
        if not path.exists():
            if not create:
                raise MoodleError(ErrorCode.AUTH_REQUIRED, "Reconnect with tum-mcp login.")
            if any(root.glob("*.enc")):
                raise MoodleError(
                    ErrorCode.SETUP_REQUIRED, "Credential key is missing; preserve backups."
                )
            private_write(path, Fernet.generate_key())
        try:
            info = path.stat()
            if os.name == "nt":
                _secure_windows_path(path.resolve())
            elif info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise MoodleError(
                    ErrorCode.SETUP_REQUIRED, "Credential key must be an owner-only file."
                )
            if not stat.S_ISREG(info.st_mode):
                raise MoodleError(
                    ErrorCode.SETUP_REQUIRED, "Credential key must be a regular file."
                )
            return Fernet(path.read_bytes())
        except (ValueError, OSError):
            raise MoodleError(
                ErrorCode.SETUP_REQUIRED, "Credential key is unreadable or damaged."
            ) from None

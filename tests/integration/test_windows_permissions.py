import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tum_moodle.secret_files import _secure_windows_path, local_cipher

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Requires native Windows ACLs.")


@pytest.mark.parametrize("consumer_environment", [False, True])
@pytest.mark.parametrize("shell", ["powershell.exe", "pwsh.exe"])
def test_native_windows_key_has_a_protected_current_user_only_acl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consumer_environment: bool, shell: str
) -> None:
    original_run = subprocess.run
    original_which = shutil.which
    if not original_which(shell):
        pytest.skip(f"Optional {shell} is not installed in this Windows profile.")
    monkeypatch.setattr(
        shutil, "which", lambda name: original_which(name) if name == shell else None
    )
    allowed = {
        "PATH",
        "HOME",
        "USERPROFILE",
        "SYSTEMROOT",
        "COMSPEC",
        "TMPDIR",
        "TMP",
        "TEMP",
        "LOCALAPPDATA",
        "APPDATA",
        "UV_CACHE_DIR",
        "UV_PYTHON_INSTALL_DIR",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "TUM_MCP_PRIVATE_DIRECTORY",
    }

    def checked_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if consumer_environment and "env" in kwargs:
            kwargs["env"] = {
                name: value for name, value in kwargs["env"].items() if name.upper() in allowed
            }
        started = time.monotonic()
        try:
            return original_run(*args, **kwargs)
        except subprocess.CalledProcessError as error:
            pytest.fail(
                f"Synthetic Windows ACL operation failed: {error.stderr.decode(errors='replace')}"
            )
        except subprocess.TimeoutExpired:
            pytest.fail(
                f"Synthetic Windows ACL operation timed out after {time.monotonic() - started:.1f}s"
            )

    monkeypatch.setattr(subprocess, "run", checked_run)
    _secure_windows_path.cache_clear()
    root = tmp_path / "private directory München"
    cipher = local_cipher(root, create=True)
    assert local_cipher(root).decrypt(cipher.encrypt(b"synthetic-only")) == b"synthetic-only"
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    assert powershell
    script = (
        "$ErrorActionPreference='Stop'; "
        "$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User; "
        "$path=$env:TUM_MCP_PRIVATE_DIRECTORY; "
        "$directory=[System.IO.Directory]::Exists($path); "
        "$acl=if($PSVersionTable.PSEdition -eq 'Core'){"
        "$item=if($directory){[System.IO.DirectoryInfo]::new($path)}"
        "else{[System.IO.FileInfo]::new($path)}; "
        "[System.IO.FileSystemAclExtensions]::GetAccessControl($item)"
        "}elseif($directory){[System.IO.Directory]::GetAccessControl($path)}"
        "else{[System.IO.File]::GetAccessControl($path)}; "
        "$rules=@($acl.GetAccessRules($true,$true,"
        "[System.Security.Principal.SecurityIdentifier])); "
        "[bool]($acl.AreAccessRulesProtected -and $rules.Count -eq 1 -and "
        "$rules[0].IdentityReference -eq $sid -and -not $rules[0].IsInherited -and "
        "$rules[0].AccessControlType -eq 'Allow')"
    )
    for path in (root, root / "session.key"):
        result = checked_run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "TUM_MCP_PRIVATE_DIRECTORY": str(path)},
            capture_output=True,
            timeout=10,
            check=True,
        )
        assert result.stdout.strip() == b"True"

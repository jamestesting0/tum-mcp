"""An isolated Windows Playwright driver over WSL interop's private stdio pipes."""

import base64
import hashlib
import io
import os
import platform
import shlex
import shutil
import socket
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

import httpx2
from filelock import FileLock, Timeout

from tum_moodle.browsers import BrowserChoice, BrowserSetupError, is_wsl, windows_host, wsl_path
from tum_moodle.config import private_write
from tum_moodle.platforms import app_root

NODE_VERSION: Final = "22.23.3"
NODE_HASHES: Final = {
    "x64": (
        "2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71",
        "9c9245166b4a8e182e0b797da9c20136117ff24368eaff1fec8343a123c8db0e",
    ),
    "arm64": (
        "33dad22e4cef5ee8f9fbb1b0d037fdacd0e56d12a4580f0d63f68b894deab535",
        "b5a3165ec6f24c0b1fe2a10fed58e03f6c1d7d141beb3b225ff030ceac6c5eb5",
    ),
}
MAX_ARCHIVE: Final = 80 * 1024 * 1024
MAX_EXECUTABLE: Final = 128 * 1024 * 1024


def _wsl1_relay(node: Path, entrypoint: str, bootstrap: str) -> str:
    """Give Windows Node real Windows pipes; WSL 1 handles cannot be opened by libuv."""
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if shell is None:
        raise BrowserSetupError("WSL 1 browser sign-in requires Windows PowerShell interop.")
    executable = wsl_path(str(node), windows=True).replace("'", "''")
    arguments = subprocess.list2cmdline(["--eval", bootstrap, entrypoint, "run-driver"]).replace(
        "'", "''"
    )
    script = (
        "$ErrorActionPreference='Stop'; $p=[Diagnostics.Process]::new(); $started=$false; "
        f"$p.StartInfo.FileName='{executable}'; $p.StartInfo.Arguments='{arguments}'; "
        "$p.StartInfo.UseShellExecute=$false; $p.StartInfo.CreateNoWindow=$true; "
        "$p.StartInfo.RedirectStandardInput=$true; $p.StartInfo.RedirectStandardOutput=$true; "
        "$p.StartInfo.RedirectStandardError=$true; "
        "try{ $started=$p.Start(); "
        "$inputCopy=[Console]::OpenStandardInput().CopyToAsync($p.StandardInput.BaseStream); "
        "$outputCopy=$p.StandardOutput.BaseStream.CopyToAsync([Console]::OpenStandardOutput()); "
        "$errorCopy=$p.StandardError.BaseStream.CopyToAsync([Console]::OpenStandardError()); "
        "$closed=$false; "
        "while(-not $p.WaitForExit(50)){if($inputCopy.IsCompleted -and -not $closed){"
        "$p.StandardInput.Close(); $closed=$true}}; "
        "$outputCopy.GetAwaiter().GetResult(); $errorCopy.GetAwaiter().GetResult(); "
        "$code=$p.ExitCode "
        "}finally{if($started -and -not $p.HasExited){$p.StandardInput.Close(); "
        "if(-not $p.WaitForExit(5000)){$p.Kill()}}; $p.Dispose()}; exit $code"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return f"exec {shlex.quote(shell)} -NoProfile -NonInteractive -EncodedCommand {encoded}\n"


def _download_node(architecture: str) -> bytes:
    archive_hash, executable_hash = NODE_HASHES[architecture]
    archive_name = f"node-v{NODE_VERSION}-win-{architecture}"
    transport = httpx2.HTTPTransport(
        http2=True,
        retries=3,
        limits=httpx2.Limits(max_connections=1, max_keepalive_connections=1, keepalive_expiry=30),
        socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
    )
    try:
        with httpx2.Client(
            transport=transport,
            timeout=httpx2.Timeout(connect=5, read=30, write=10, pool=10),
            follow_redirects=False,
        ) as client:
            with client.stream(
                "GET", f"https://nodejs.org/dist/v{NODE_VERSION}/{archive_name}.zip"
            ) as response:
                response.raise_for_status()
                archive = bytearray()
                for chunk in response.iter_bytes():
                    if len(archive) + len(chunk) > MAX_ARCHIVE:
                        raise BrowserSetupError(
                            "The Windows browser runtime exceeded its download budget."
                        )
                    archive.extend(chunk)
        if hashlib.sha256(archive).hexdigest() != archive_hash:
            raise BrowserSetupError(
                "Windows browser runtime checksum failed. Retry setup on a trusted network."
            )
        with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
            member = bundle.getinfo(f"{archive_name}/node.exe")
            if member.file_size > MAX_EXECUTABLE:
                raise BrowserSetupError(
                    "The Windows browser runtime exceeded its extraction budget."
                )
            executable = bundle.read(member)
        if hashlib.sha256(executable).hexdigest() != executable_hash:
            raise BrowserSetupError("The extracted Windows browser runtime checksum failed.")
        return executable
    except (httpx2.HTTPError, zipfile.BadZipFile, KeyError, OSError):
        raise BrowserSetupError(
            "Could not prepare the Windows browser runtime. "
            "Check access to nodejs.org, then retry connect."
        ) from None


def windows_node() -> Path:
    host = windows_host()
    directory = (
        host.local_data / "TUMMCP" / "browser-runtime" / f"node-{NODE_VERSION}-{host.architecture}"
    )
    executable = Path(wsl_path(str(directory / "node.exe")))
    locks = app_root().with_name("TUMMCP") / "browser-runtime"
    try:
        locks.mkdir(mode=0o700, parents=True, exist_ok=True)
        with FileLock(str(locks / "windows-node.lock"), timeout=120):
            if executable.is_symlink():
                raise BrowserSetupError(
                    "The managed Windows browser runtime cannot be a symbolic link."
                )
            expected = NODE_HASHES[host.architecture][1]
            if (
                executable.is_file()
                and executable.stat().st_size <= MAX_EXECUTABLE
                and hashlib.sha256(executable.read_bytes()).hexdigest() == expected
            ):
                executable.chmod(0o700)
                return executable
            executable.parent.mkdir(parents=True, exist_ok=True)
            private_write(executable, _download_node(host.architecture))
            executable.chmod(0o700)
            return executable
    except (OSError, Timeout):
        raise BrowserSetupError(
            "Could not save the private Windows browser runtime; check file permissions."
        ) from None


@contextmanager
def browser_driver(browser: BrowserChoice) -> Iterator[None]:
    """Preserve caller environment, keep credentials in pipes, and remove the temporary shim."""
    keys = ("PLAYWRIGHT_NODEJS_PATH", "DEBUG", "DEBUGP", "PWDEBUG")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        for key in keys[1:]:
            os.environ.pop(key, None)
        with tempfile.TemporaryDirectory(prefix="tum-browser-driver-") as temporary:
            if browser.windows_host:
                import playwright

                node = windows_node()
                cli = Path(playwright.__file__).parent / "driver/package/cli.js"
                entrypoint = wsl_path(str(cli), windows=True)
                bootstrap = (
                    "for(const key of ['DEBUG','DEBUGP','PWDEBUG'])delete process.env[key];"
                    "require(process.argv[1]);"
                )
                shim = Path(temporary) / "windows-node"
                command = (
                    _wsl1_relay(node, entrypoint, bootstrap)
                    if is_wsl() and "wsl2" not in platform.release().lower()
                    else f"exec {shlex.quote(str(node))} --eval {shlex.quote(bootstrap)} "
                    f'{shlex.quote(entrypoint)} "$@"\n'
                )
                private_write(shim, ("#!/bin/sh\nshift\n" + command).encode())
                shim.chmod(0o700)
                os.environ["PLAYWRIGHT_NODEJS_PATH"] = str(shim)
            yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

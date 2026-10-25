"""An isolated Windows Playwright driver over WSL interop's private stdio pipes."""

import base64
import hashlib
import io
import os
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

from tum_mcp.moodle.browsers import BrowserChoice, BrowserSetupError, windows_host, wsl_path
from tum_mcp.moodle.config import private_write
from tum_mcp.moodle.platforms import app_root

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


def _direct_pipes_work(node: Path) -> bool:
    """Probe binary stdio capability, independent of WSL package or engine versions."""
    payload = b"tum-browser-pipe\x00\xff\n"
    script = "process.stdin.pipe(process.stdout);"
    try:
        result = subprocess.run(  # noqa: S603
            [str(node), "--eval", script], input=payload, capture_output=True, timeout=10
        )
        return result.returncode == 0 and result.stdout == payload
    except (OSError, subprocess.SubprocessError):
        return False


def _native_pipe_relay(node: Path, entrypoint: str, bootstrap: str) -> str:
    """Give Windows Node native handles and copy binary data on independent threads."""
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if shell is None:
        raise BrowserSetupError("Windows browser sign-in requires Windows PowerShell interop.")
    executable = wsl_path(str(node), windows=True).replace("'", "''")
    arguments = subprocess.list2cmdline(["--eval", bootstrap, entrypoint, "run-driver"]).replace(
        "'", "''"
    )
    # Console streams on Windows PowerShell can synchronously block CopyToAsync.
    # C# threads avoid PowerShell runspace callbacks and keep all three streams live.
    source = """using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
public static class TumBrowserPipes {
  static Thread Copy(Stream source, Stream target, bool close) {
    var thread = new Thread(() => {
      try {
        var buffer = new byte[8192]; int count;
        while ((count = source.Read(buffer, 0, buffer.Length)) > 0) {
          target.Write(buffer, 0, count); target.Flush();
        }
      }
      catch (IOException) {} catch (ObjectDisposedException) {}
      finally { if (close) target.Dispose(); }
    });
    thread.IsBackground = true; thread.Start(); return thread;
  }
  public static int Run(string executable, string arguments) {
    // Process.StandardInput derives its StreamWriter encoding from the console.
    // A BOM here would corrupt the first binary Playwright frame.
    Console.InputEncoding = new System.Text.UTF8Encoding(false);
    using (var process = new Process()) {
      process.StartInfo = new ProcessStartInfo(executable, arguments) {
        UseShellExecute = false, CreateNoWindow = true,
        RedirectStandardInput = true, RedirectStandardOutput = true,
        RedirectStandardError = true
      };
      process.Start();
      try {
        Copy(Console.OpenStandardInput(), process.StandardInput.BaseStream, true);
        var output = Copy(process.StandardOutput.BaseStream, Console.OpenStandardOutput(), false);
        var error = Copy(process.StandardError.BaseStream, Console.OpenStandardError(), false);
        process.WaitForExit(); output.Join(); error.Join(); return process.ExitCode;
      } finally { if (!process.HasExited) process.Kill(); }
    }
  }
}"""
    source64 = base64.b64encode(source.encode()).decode("ascii")
    script = (
        "$ErrorActionPreference='Stop'; "
        "Import-Module ([IO.Path]::Combine($PSHOME,'Modules','Microsoft.PowerShell.Utility',"
        "'Microsoft.PowerShell.Utility.psd1')); "
        f"Add-Type -TypeDefinition ([Text.Encoding]::UTF8.GetString("
        f"[Convert]::FromBase64String('{source64}'))); "
        f"exit [TumBrowserPipes]::Run('{executable}','{arguments}')"
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
                    _native_pipe_relay(node, entrypoint, bootstrap)
                    if not _direct_pipes_work(node)
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

"""Bounded, credential-free subprocess boundary for the optional recognizer."""

import os
import subprocess
from pathlib import Path

from tum_mcp.errors import CampusError, Code


def isolated_run(argv: tuple[str, ...], payload: bytes = b"", timeout: int = 1200) -> bytes:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "PATH", "TMPDIR", "SYSTEMROOT", "LANG", "LC_ALL", "HF_HUB_CACHE"}
    }
    environment.update(HF_HUB_DISABLE_TELEMETRY="1", TOKENIZERS_PARALLELISM="false")
    try:
        # Fixed executable/worker paths and validated local data, with no shell or campus state.
        with subprocess.Popen(  # noqa: S603
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=environment,
        ) as child:
            try:
                output, _ = child.communicate(payload, timeout=timeout)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
            if child.returncode or len(output) > 8 * 1024 * 1024:
                raise CampusError(
                    Code.CAPABILITY_UNSUPPORTED,
                    "Optional lecture runtime failed; private diagnostics omitted.",
                )
            return output
    except (OSError, subprocess.TimeoutExpired):
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED,
            "Optional lecture runtime unavailable or timed out; checkpoint retained.",
        ) from None


def worker_path() -> Path:
    return Path(__file__).parents[1] / "bundled/lecture_runtime/worker.py"

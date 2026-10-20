import os
import resource
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import psutil

from tum_moodle.errors import ErrorCode, MoodleError
from tum_moodle.extraction import extract
from tum_moodle.models import Extracted


def run_extraction(body: bytes, content_type: str) -> Extracted:
    with tempfile.TemporaryDirectory(prefix="tum-moodle-extract-") as directory:
        path = Path(directory) / "document"
        path.write_bytes(body)
        with subprocess.Popen(
            [sys.executable, "-m", "tum_moodle.extract_worker", str(path), content_type],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        ) as process:
            deadline = time.monotonic() + 60
            observed = psutil.Process(process.pid)
            while True:
                try:
                    output, _ = process.communicate(timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    try:
                        memory = sum(
                            child.memory_info().rss
                            for child in [observed, *observed.children(recursive=True)]
                        )
                    except psutil.NoSuchProcess:
                        memory = 0
                    if memory > 512 * 1024**2 or time.monotonic() > deadline:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.communicate()
                        raise MoodleError(
                            ErrorCode.EXTRACTION_FAILED,
                            "Document exceeded extraction time or memory limits.",
                        ) from None
            if process.returncode != 0:
                raise MoodleError(ErrorCode.EXTRACTION_FAILED, "Document could not be extracted.")
            return Extracted.model_validate_json(output)


if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    result = extract(Path(sys.argv[1]).read_bytes(), sys.argv[2])
    sys.stdout.write(result.model_dump_json())

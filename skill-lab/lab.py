"""Entry point: uv run skill-lab/lab.py <command>."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from skill_lab.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())

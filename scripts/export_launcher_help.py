"""Write npm/help.json, the help the npm launcher shows before the Python runtime exists."""

import json
from pathlib import Path

from tum_mcp.cli import app
from tum_mcp.commands.help import launcher_help

TARGET = Path(__file__).resolve().parents[1] / "npm" / "help.json"

if __name__ == "__main__":
    _ = TARGET.write_text(json.dumps(launcher_help(app), indent=2) + "\n", encoding="utf-8")
    print(TARGET)

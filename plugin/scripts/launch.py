import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
from tum_moodle.platforms import runtime_python  # noqa: E402

runtime = runtime_python()
if not runtime.is_file():
    sys.exit("TUM Moodle setup is required. Run the plugin's setup skill first.")
command = [str(runtime), "-m", "tum_moodle", "serve"]
if os.name == "nt":
    sys.exit(subprocess.call(command))
os.execv(str(runtime), command)

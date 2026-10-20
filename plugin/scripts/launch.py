import os
import sys
from pathlib import Path

runtime = Path.home() / "Library/Application Support/TUMMoodle/runtime/bin/python"
if not runtime.is_file():
    sys.exit("TUM Moodle setup is required. Run the plugin's setup skill first.")
os.execv(str(runtime), [str(runtime), "-m", "tum_moodle", "serve"])

import json
import shutil
import sys
from pathlib import Path


def build_package(root: Path) -> Path:
    destination = root / "dist/tum-moodle"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(root / "plugin", destination)
    shutil.copytree(
        root / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("pyproject.toml", "uv.lock", "README.md", ".python-version", "LICENSE", "NOTICE"):
        shutil.copy2(root / name, destination / name)
    return destination


def register_package(package: Path) -> Path:
    source = Path.home() / ".codex/plugins/local/tum-moodle"
    if source.exists():
        shutil.rmtree(source)
    shutil.copytree(package, source)
    marketplace_path = Path.home() / ".agents/plugins/marketplace.json"
    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace = (
        json.loads(marketplace_path.read_text())
        if marketplace_path.exists()
        else {
            "name": "personal-local",
            "interface": {"displayName": "Personal local plugins"},
            "plugins": [],
        }
    )
    entry = {
        "name": "tum-moodle",
        "source": {"source": "local", "path": "./" + str(source.relative_to(Path.home()))},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Education",
    }
    entries = [item for item in marketplace["plugins"] if item["name"] != "tum-moodle"]
    marketplace["plugins"] = [*entries, entry]
    marketplace_path.write_text(json.dumps(marketplace, indent=2) + "\n")
    return marketplace_path


if __name__ == "__main__":
    package = build_package(Path(__file__).resolve().parents[1])
    print(f"Packaged: {package}")
    if "--register" in sys.argv:
        print(f"Marketplace: {register_package(package)}")

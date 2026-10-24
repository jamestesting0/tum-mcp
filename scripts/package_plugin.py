import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from tum_moodle.platforms import runtime_python  # noqa: E402


def build_package(root: Path) -> Path:
    destination = root / "dist/tum-moodle"
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(
        root / "plugin", destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    documentation = destination / "docs"
    documentation.mkdir()
    for name in ("setup.md", "development.md", "tum-mcp.md"):
        shutil.copy2(root / "docs" / name, documentation / name)
    manifest_path = destination / "mcp.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    server = manifest["mcpServers"]["moodle"]
    server["command"] = str(runtime_python())
    server["args"] = ["-m", "tum_moodle", "serve"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    shutil.copytree(
        root / "src",
        destination / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("pyproject.toml", "uv.lock", "README.md", ".python-version", "LICENSE", "NOTICE"):
        shutil.copy2(root / name, destination / name)
    return destination


def register_package(package: Path, *, replace_source: bool = True) -> Path:
    source = Path.home() / ".codex/plugins/local/tum-moodle"
    if replace_source or not source.is_dir():
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
        "source": {"source": "local", "path": "./" + source.relative_to(Path.home()).as_posix()},
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

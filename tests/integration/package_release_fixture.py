# /// script
# requires-python = ">=3.13"
# ///
# Run with the isolated consumer's Python: package_release_fixture.py INPUT OUTPUT VERSION
"""Create an unpublished synthetic next-release wheel for package lifecycle checks."""

import base64
import csv
import hashlib
import io
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main() -> None:
    source, destination, version = sys.argv[1:]
    with ZipFile(source) as archive:
        old = next(
            name.split("/")[0]
            for name in archive.namelist()
            if name.endswith(".dist-info/METADATA")
        )
        new = f"tum_mcp-{version}.dist-info"
        contents = {
            name.replace(old + "/", new + "/"): archive.read(name)
            for name in archive.namelist()
            if not name.endswith(".dist-info/RECORD")
        }
    contents["tum_mcp/__init__.py"] = f'__version__ = "{version}"\n'.encode()
    metadata = contents[new + "/METADATA"].decode()
    lines = metadata.splitlines(keepends=True)
    contents[new + "/METADATA"] = "".join(
        f"Version: {version}\n" if line.startswith("Version: ") else line for line in lines
    ).encode()
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, body in contents.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip("=")
        writer.writerow((name, "sha256=" + digest, len(body)))
    writer.writerow((new + "/RECORD", "", ""))
    contents[new + "/RECORD"] = record.getvalue().encode()
    with ZipFile(Path(destination), "w", compression=ZIP_DEFLATED) as archive:
        for name, body in contents.items():
            archive.writestr(name, body)


if __name__ == "__main__":
    main()

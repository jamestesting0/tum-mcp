import json
import shutil
from pathlib import Path

from tum_mcp.course.content.store import LAYOUTS, present, read_document, write_document
from tum_mcp.course.project.store import confined


class Document:
    """A workspace document that tests read and write as one JSON value, as authors did."""

    def __init__(self, root: Path, workspace: str) -> None:
        self.root, self.workspace = root, workspace

    def read_bytes(self) -> bytes:
        document = read_document(self.root, self.workspace)
        if document is None:
            raise FileNotFoundError(self.workspace)
        return json.dumps(document, ensure_ascii=False).encode()

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.read_bytes().decode(encoding)

    def write_text(self, text: str, encoding: str = "utf-8") -> None:
        write_document(self.root, self.workspace, json.loads(text))

    def write_bytes(self, data: bytes) -> None:
        self.write_text(data.decode())

    def exists(self) -> bool:
        return present(self.root, self.workspace)

    is_file = exists

    def unlink(self) -> None:
        shutil.rmtree(confined(self.root, f"app/{LAYOUTS[self.workspace].folder}"))


def content_file(root: Path, workspace: str) -> Document:
    return Document(root, workspace)

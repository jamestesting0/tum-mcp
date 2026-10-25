from pathlib import Path

from tum_mcp.moodle.config import Paths
from tum_mcp.moodle.library import Library
from tum_mcp.moodle.models import Extracted, Material, TextPage


def material() -> Material:
    return Material(
        id="module:1",
        course_id=7,
        title="Timing",
        kind="resource",
        url="https://www.moodle.tum.de/mod/resource/view.php?id=1",
    )


def test_refresh_replaces_indexed_text(tmp_path: Path) -> None:
    library = Library(Paths(tmp_path), "account-1")
    item = material()
    library.put_materials([item])
    library.put_content(item, Extracted(pages=[TextPage(number=2, text="old deadline")]))
    assert library.search("deadline", 7, 20)[0].number == 2
    library.put_content(item, Extracted(pages=[TextPage(number=3, text="new scheduling")]))
    assert library.search("deadline", 7, 20) == []
    assert library.search("scheduling", 7, 20)[0].number == 3


def test_account_change_purges_previous_content(tmp_path: Path) -> None:
    library = Library(Paths(tmp_path), "account-1")
    item = material()
    library.put_materials([item])
    library.put_content(item, Extracted(pages=[TextPage(number=1, text="private")]), b"content")
    replacement = Library(Paths(tmp_path), "account-2")
    assert replacement.coverage(7) == {"discovered": 0, "indexed": 0, "pending": 0}
    assert list((tmp_path / "files").iterdir()) == []


def test_deleted_material_disappears_from_search(tmp_path: Path) -> None:
    library = Library(Paths(tmp_path), "account-1")
    item = material()
    library.put_materials([item])
    library.put_content(item, Extracted(pages=[TextPage(number=1, text="private")]))
    library.put_materials([], replace_course=7)
    assert library.search("private", 7, 20) == []


def test_refresh_preserves_children_of_live_folders(tmp_path: Path) -> None:
    library = Library(Paths(tmp_path), "account-1")
    parent = material()
    child = Material(
        id="file:2", course_id=7, title="Child", kind="file", url="", parent_id=parent.id
    )
    library.put_materials([parent, child])
    library.put_materials([parent], replace_course=7)
    assert library.material(child.id) == child
    library.put_materials([], replace_course=7)
    assert library.materials(7) == []

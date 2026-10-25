import hashlib
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from tum_mcp.moodle.config import CACHE_BYTES, CACHE_DAYS, Paths, private_write
from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.models import Extracted, Material, SearchHit


class Library:
    def __init__(self, paths: Paths, generation: str) -> None:
        self.paths = paths
        self.database = paths.file("library.sqlite")
        self.files = paths.file("files")
        if self.files.is_symlink() or self.database.is_symlink():
            raise MoodleError(ErrorCode.SETUP_REQUIRED, "The private cache must not be a symlink.")
        self.files.mkdir(mode=0o700, exist_ok=True)
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account (generation TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS materials (
                    id TEXT PRIMARY KEY, course INTEGER, data TEXT NOT NULL,
                    fetched REAL, extracted TEXT, blob TEXT, size INTEGER DEFAULT 0);
                CREATE VIRTUAL TABLE IF NOT EXISTS search USING fts5(
                    material UNINDEXED, page UNINDEXED, text);
            """)
            account = db.execute("SELECT generation FROM account").fetchone()
            if account is None or account[0] != generation:
                self._clear(db)
                db.execute("DELETE FROM account")
                db.execute("INSERT INTO account VALUES (?)", (generation,))
            self._expire(db)
        self.database.chmod(0o600)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=30)

    def _remove(self, db: sqlite3.Connection, identity: str) -> None:
        row = db.execute("SELECT blob FROM materials WHERE id=?", (identity,)).fetchone()
        if row and row[0]:
            (self.files / Path(row[0]).name).unlink(missing_ok=True)
        db.execute("DELETE FROM search WHERE material=?", (identity,))
        db.execute("DELETE FROM materials WHERE id=?", (identity,))

    def _clear(self, db: sqlite3.Connection) -> None:
        for (identity,) in db.execute("SELECT id FROM materials").fetchall():
            self._remove(db, identity)
        for path in self.files.iterdir():
            if path.is_file() or path.is_symlink():
                path.unlink()

    def clear(self) -> None:
        with closing(self.connect()) as db, db:
            self._clear(db)
            db.commit()
            db.execute("VACUUM")

    def _expire(self, db: sqlite3.Connection) -> None:
        cutoff = time.time() - CACHE_DAYS * 86400
        removed = False
        for (identity,) in db.execute(
            "SELECT id FROM materials WHERE fetched IS NOT NULL AND fetched < ?", (cutoff,)
        ).fetchall():
            self._remove(db, identity)
            removed = True
        for (identity,) in db.execute(
            "SELECT id FROM materials WHERE fetched IS NOT NULL ORDER BY fetched"
        ).fetchall():
            pages = db.execute("PRAGMA page_count").fetchone()[0]
            free = db.execute("PRAGMA freelist_count").fetchone()[0]
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            file_bytes = sum(path.stat().st_size for path in self.files.iterdir() if path.is_file())
            if (pages - free) * page_size + file_bytes <= CACHE_BYTES:
                break
            self._remove(db, identity)
            removed = True
        if removed:
            db.commit()
            db.execute("VACUUM")

    def put_materials(
        self, materials: list[Material], *, replace_course: int | None = None
    ) -> None:
        with closing(self.connect()) as db, db:
            if replace_course is not None:
                ids = {material.id for material in materials}
                existing = [
                    Material.model_validate_json(row[0])
                    for row in db.execute(
                        "SELECT data FROM materials WHERE course=?", (replace_course,)
                    ).fetchall()
                ]
                for _ in range(len(existing)):
                    reachable = {item.id for item in existing if item.parent_id in ids}
                    if reachable <= ids:
                        break
                    ids.update(reachable)
                for item in existing:
                    identity = item.id
                    if identity not in ids:
                        self._remove(db, identity)
            db.executemany(
                "INSERT INTO materials(id,course,data) VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data,course=excluded.course",
                [
                    (material.id, material.course_id, material.model_dump_json())
                    for material in materials
                ],
            )

    def material(self, identity: str) -> Material:
        with closing(self.connect()) as db:
            row = db.execute("SELECT data FROM materials WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise MoodleError(ErrorCode.NOT_FOUND, "List this course's materials first.")
        return Material.model_validate_json(row[0])

    def materials(self, course_id: int) -> list[Material]:
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT data FROM materials WHERE course=? ORDER BY rowid", (course_id,)
            ).fetchall()
        return [Material.model_validate_json(row[0]) for row in rows]

    def put_content(self, material: Material, extracted: Extracted, body: bytes = b"") -> None:
        blob = ""
        if body:
            suffix = ".pdf" if body.startswith(b"%PDF-") else ".bin"
            blob = hashlib.sha256(material.id.encode()).hexdigest() + suffix
            private_write(self.files / blob, body)
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM search WHERE material=?", (material.id,))
            db.execute(
                "UPDATE materials SET fetched=?,extracted=?,blob=?,size=? WHERE id=?",
                (time.time(), extracted.model_dump_json(), blob, len(body), material.id),
            )
            db.executemany(
                "INSERT INTO search(material,page,text) VALUES (?,?,?)",
                [(material.id, page.number, page.text) for page in extracted.pages],
            )
            self._expire(db)

    def content(self, identity: str) -> tuple[Extracted, float] | None:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT extracted,fetched FROM materials WHERE id=?", (identity,)
            ).fetchone()
        if row is None or row[0] is None:
            return None
        return Extracted.model_validate_json(row[0]), row[1]

    def blob(self, identity: str) -> Path | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT blob FROM materials WHERE id=?", (identity,)).fetchone()
        return self.files / Path(row[0]).name if row and row[0] else None

    def coverage(self, course_id: int) -> dict[str, int]:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT COUNT(*),COUNT(extracted) FROM materials WHERE course=?", (course_id,)
            ).fetchone()
        return {"discovered": row[0], "indexed": row[1], "pending": row[0] - row[1]}

    def search(self, query: str, course_id: int, limit: int) -> list[SearchHit]:
        tokens = query.split()[:20]
        if not tokens:
            return []
        expression = " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)
        with closing(self.connect()) as db:
            rows = db.execute(
                "SELECT m.data,s.page,snippet(search,2,'','', ' ... ',48) "
                "FROM search s JOIN materials m ON m.id=s.material "
                "WHERE search MATCH ? AND m.course=? "
                "AND json_extract(m.data,'$.kind') NOT LIKE 'private_%' ORDER BY rank LIMIT ?",
                (expression, course_id, limit),
            ).fetchall()
        return [
            SearchHit(
                material_id=(m := Material.model_validate_json(row[0])).id,
                title=m.title,
                url=m.url,
                number=int(row[1]),
                text=row[2],
            )
            for row in rows
        ]

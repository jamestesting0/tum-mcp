import time

from pydantic import JsonValue

from tum_mcp.moodle.auth import SessionStore
from tum_mcp.moodle.config import Paths
from tum_mcp.moodle.downloads import save_download
from tum_mcp.moodle.errors import ErrorCode, MoodleError
from tum_mcp.moodle.extract_worker import run_extraction
from tum_mcp.moodle.forums import posts_from_api
from tum_mcp.moodle.http_client import Download, MoodleHTTP
from tum_mcp.moodle.library import Library
from tum_mcp.moodle.models import Extracted, Material, TextPage
from tum_mcp.moodle.moodle import Moodle
from tum_mcp.moodle.parsing import (
    discussions_from_html,
    files_from_html,
    linked_pages_from_html,
)


class Service:
    def __init__(self) -> None:
        self.store = SessionStore(Paths.default())
        session = self.store.load()
        self.generation = session.generation
        self.http = MoodleHTTP(self.store)
        self.moodle = Moodle(self.http)
        self.library = Library(self.store.paths, session.generation)

    def check_generation(self) -> None:
        if self.generation != self.store.generation():
            raise MoodleError(ErrorCode.SESSION_EXPIRED, "The session was disconnected.")

    def courses(self) -> dict[str, JsonValue]:
        term, courses, ambiguous = self.moodle.courses()
        return {
            "semester": term,
            "courses": [course.model_dump(mode="json") for course in courses],
            "unclassified": [course.model_dump(mode="json") for course in ambiguous],
            "checked_at": time.time(),
        }

    def materials(self, course_id: int) -> list[Material]:
        roots = self.moodle.materials(course_id)
        self.library.put_materials(roots, replace_course=course_id)
        return [
            item
            for item in self.library.materials(course_id)
            if not item.kind.startswith("private_")
        ]

    def require_material(self, identity: str) -> Material:
        material = self.library.material(identity)
        self.moodle.require_course(material.course_id)
        self.check_generation()
        return material

    def expand(self, material: Material, page: int = 0) -> tuple[list[Material], bool]:
        url = material.url + (f"&p={page}" if page else "")
        html = self.http.get(url).text()
        children = (
            discussions_from_html(html, material)
            if material.kind == "forum"
            else files_from_html(html, material)
        )
        self.library.put_materials(children)
        has_more = f"p={page + 1}" in html or f"page={page + 1}" in html
        return children, has_more

    def discussion(self, identity: str) -> dict[str, JsonValue]:
        material = self.require_material(identity)
        if material.kind != "discussion":
            raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Choose a forum discussion.")
        value = self.http.read_api(
            "mod_forum_get_discussion_posts",
            {
                "discussionid": int(identity.split(":")[1]),
                "sortby": "created",
                "sortdirection": "ASC",
            },
        )
        posts = posts_from_api(value, material)
        attachments = [attachment for post in posts for attachment in post.attachments]
        self.library.put_materials(attachments)
        extracted = Extracted(
            pages=[
                TextPage(number=i, text=post.text, unit="post") for i, post in enumerate(posts, 1)
            ]
        )
        self.library.put_content(material, extracted)
        self.check_generation()
        return {
            "discussion": material.model_dump(mode="json"),
            "posts": [post.model_dump(mode="json") for post in posts],
            "fetched_at": time.time(),
        }

    def extract(
        self, material: Material, response: Download | None = None
    ) -> tuple[Extracted, bytes]:
        if material.kind == "url":
            return Extracted(
                pages=[TextPage(number=1, text=material.url, unit="section")],
                warnings=["LINK_ONLY: open the source/player link; no transcript."],
            ), b""
        if material.kind == "label":
            return Extracted(
                pages=[TextPage(number=1, text=material.inline_text, unit="section")]
            ), b""
        if material.kind == "discussion":
            self.discussion(material.id)
            content = self.library.content(material.id)
            return (content[0] if content else Extracted()), b""
        allowed = {
            "resource",
            "file",
            "page",
            "book",
            "folder",
            "forum",
            "assign",
            "glossary",
            "wiki",
            "quiz",
            "choice",
            "private_file",
        }
        if material.kind not in allowed:
            raise MoodleError(
                ErrorCode.RESOURCE_UNSUPPORTED,
                f"Interactive activity type '{material.kind}' is not opened automatically.",
            )
        download = response or self.http.get(material.url)
        if download.content_type.startswith(("video/", "audio/")):
            return Extracted(
                pages=[TextPage(number=1, text=material.url, unit="section")],
                warnings=["LINK_ONLY: recordings are not downloaded or transcribed."],
            ), b""
        if "html" in download.content_type:
            self.library.put_materials(files_from_html(download.text(), material))
            if material.kind in {"book", "wiki"}:
                self.library.put_materials(linked_pages_from_html(download.text(), material))
        extracted = run_extraction(download.body, download.content_type)
        return extracted, download.body

    def read(self, identity: str, *, refresh: bool = False) -> tuple[Material, Extracted, float]:
        material = self.require_material(identity)
        cached = None if refresh else self.library.content(identity)
        response = None
        if material.kind not in {"url", "label", "discussion"}:
            response = self.http.get(material.url)
        blob = self.library.blob(identity)
        unchanged = (
            response is not None
            and blob is not None
            and blob.is_file()
            and blob.read_bytes() == response.body
        )
        if cached and unchanged:
            extracted, timestamp = cached
        else:
            extracted, body = self.extract(material, response)
            self.library.put_content(material, extracted, body)
            timestamp = time.time()
        self.check_generation()
        return material, extracted, timestamp

    def refresh(self, course_id: int, scope: str, offset: int, limit: int) -> dict[str, JsonValue]:
        roots = self.materials(course_id)
        errors: list[JsonValue] = []
        if scope == "metadata":
            return {
                "materials": [item.model_dump(mode="json") for item in roots],
                "coverage": self.library.coverage(course_id),
                "next_cursor": None,
            }
        deadline = time.monotonic() + 45
        snapshot = self.library.materials(course_id)
        done = offset
        for material in snapshot[offset : offset + limit]:
            if time.monotonic() > deadline:
                break
            try:
                if material.kind in {"forum", "folder"}:
                    self.expand(material)
                self.read(material.id, refresh=True)
            except MoodleError as error:
                errors.append(
                    {"material_id": material.id, "code": error.code.value, "message": error.message}
                )
            done += 1
        self.check_generation()
        count = len(self.library.materials(course_id))
        return {
            "processed": done - offset,
            "errors": errors,
            "coverage": self.library.coverage(course_id),
            "next_cursor": str(done) if done < count else None,
        }

    def download(self, identity: str) -> dict[str, JsonValue]:
        material = self.require_material(identity)
        if material.kind not in {"resource", "file", "private_file"}:
            raise MoodleError(
                ErrorCode.RESOURCE_UNSUPPORTED, "This item is read through its source link."
            )
        response = self.http.get(material.url)
        self.check_generation()
        return save_download(material, response)

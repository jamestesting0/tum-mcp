import hashlib
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from tum_mcp.moodle.config import BASE_URL
from tum_mcp.moodle.models import Material


def text_of(node: Tag) -> str:
    for child in node.select("script, style, .accesshide, .sr-only, .visually-hidden"):
        child.decompose()
    return node.get_text(" ", strip=True)


def file_id(url: str) -> str:
    return "file:" + hashlib.sha256(url.encode()).hexdigest()[:24]


def materials_from_html(html: str, course_id: int) -> list[Material]:
    soup = BeautifulSoup(html, "html.parser")
    materials: dict[str, Material] = {}
    for section in soup.select("li.section, section.section"):
        heading = section.select_one(".sectionname, h2, h3")
        title = text_of(heading) if heading else ""
        for activity in section.select(".activity"):
            anchor = next(
                (
                    a
                    for a in activity.select("a[href]")
                    if re.search(r"/mod/\w+/view\.php", str(a.get("href", "")))
                ),
                None,
            )
            if anchor is None:
                label = activity.select_one(".contentwithoutlink, .activity-altcontent")
                if label and text_of(label):
                    identity = f"section:{course_id}:{activity.get('id', file_id(str(label)))}"
                    materials[identity] = Material(
                        id=identity,
                        course_id=course_id,
                        title=title or "Course information",
                        kind="label",
                        url=f"{BASE_URL}/course/view.php?id={course_id}",
                        section=title,
                        inline_text=text_of(label),
                    )
                continue
            url = urljoin(BASE_URL, str(anchor["href"]))
            parts = urlsplit(url)
            module = re.search(r"/mod/(\w+)/view\.php", parts.path)
            identity = parse_qs(parts.query).get("id", [""])[0]
            if module and identity.isdigit():
                name = anchor.select_one(".instancename") or anchor
                material = Material(
                    id=f"module:{identity}",
                    course_id=course_id,
                    title=text_of(name),
                    kind=module[1],
                    url=url,
                    section=title,
                )
                materials[material.id] = material
    return list(materials.values())


def files_from_html(html: str, parent: Material) -> list[Material]:
    soup = BeautifulSoup(html, "html.parser")
    files: dict[str, Material] = {}
    for anchor in soup.select('a[href*="/pluginfile.php/"]'):
        url = urljoin(BASE_URL, str(anchor["href"]))
        if urlsplit(url).hostname != "www.moodle.tum.de":
            continue
        material = Material(
            id=file_id(url),
            course_id=parent.course_id,
            title=text_of(anchor) or urlsplit(url).path.rsplit("/", 1)[-1],
            kind="file",
            url=url,
            section=parent.section,
            parent_id=parent.id,
        )
        files[material.id] = material
    return list(files.values())


def linked_pages_from_html(html: str, parent: Material) -> list[Material]:
    soup = BeautifulSoup(html, "html.parser")
    pages: dict[str, Material] = {}
    for anchor in soup.select('a[href*="/mod/book/view.php"], a[href*="/mod/wiki/view.php"]'):
        url = urljoin(BASE_URL, str(anchor["href"]))
        query = parse_qs(urlsplit(url).query)
        if not ({"chapterid", "pageid"} & query.keys()) or url == parent.url:
            continue
        item = Material(
            id="page:" + file_id(url).removeprefix("file:"),
            course_id=parent.course_id,
            title=text_of(anchor),
            kind=parent.kind,
            url=url,
            parent_id=parent.id,
            section=parent.section,
        )
        pages[item.id] = item
    return list(pages.values())


def discussions_from_html(html: str, forum: Material) -> list[Material]:
    soup = BeautifulSoup(html, "html.parser")
    discussions: dict[str, Material] = {}
    for anchor in soup.select('a[href*="/mod/forum/discuss.php"]'):
        url = urljoin(BASE_URL, str(anchor["href"]))
        identity = parse_qs(urlsplit(url).query).get("d", [""])[0]
        if identity.isdigit() and f"discussion:{identity}" not in discussions:
            material = Material(
                id=f"discussion:{identity}",
                course_id=forum.course_id,
                title=text_of(anchor),
                kind="discussion",
                url=f"{BASE_URL}/mod/forum/discuss.php?d={identity}",
                section=forum.title,
                parent_id=forum.id,
            )
            discussions[material.id] = material
    return list(discussions.values())


def main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    content = soup.select_one('[role="main"], #region-main') or soup
    for element in content.select("nav, .activity-navigation, .tertiary-navigation"):
        element.decompose()
    return text_of(content)

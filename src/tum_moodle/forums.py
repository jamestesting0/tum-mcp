from pydantic import Field, JsonValue

from tum_moodle.config import BASE_URL
from tum_moodle.errors import ErrorCode, MoodleError
from tum_moodle.models import Material, Model, Post
from tum_moodle.parsing import file_id, main_text


class Author(Model):
    fullname: str = ""


class Attachment(Model):
    filename: str
    fileurl: str


class ForumPost(Model):
    id: int
    message: str = ""
    author: Author = Field(default_factory=Author)
    parentid: int | None = None
    timecreated: int = 0
    isdeleted: bool = False
    attachments: list[Attachment] = Field(default_factory=list)
    messageinlinefiles: list[Attachment] = Field(default_factory=list)


class ForumPage(Model):
    courseid: int
    posts: list[ForumPost]


def posts_from_api(value: JsonValue, discussion: Material) -> list[Post]:
    data = ForumPage.model_validate(value)
    if data.courseid != discussion.course_id:
        raise MoodleError(ErrorCode.ACCESS_DENIED, "Discussion belongs to another course.")
    return [
        Post(
            id=str(post.id),
            author=post.author.fullname,
            text="[Deleted post]" if post.isdeleted else main_text(post.message),
            url=f"{BASE_URL}/mod/forum/discuss.php?d={discussion.id.split(':')[1]}#p{post.id}",
            parent_id=str(post.parentid) if post.parentid else "",
            timestamp=str(post.timecreated),
            attachments=[
                Material(
                    id=file_id(file.fileurl),
                    course_id=discussion.course_id,
                    title=file.filename,
                    kind="file",
                    url=file.fileurl,
                    parent_id=discussion.id,
                    section=discussion.title,
                )
                for file in post.attachments + post.messageinlinefiles
            ]
            if not post.isdeleted
            else [],
        )
        for post in data.posts
    ]

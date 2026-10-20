from typing import Literal

from bs4 import BeautifulSoup
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from tum_moodle.config import BASE_URL
from tum_moodle.errors import ErrorCode, MoodleError
from tum_moodle.models import Extracted, Material, TextPage
from tum_moodle.pagination import excerpt
from tum_moodle.parsing import files_from_html, main_text
from tum_moodle.service import Service


class Member(BaseModel):
    model_config = ConfigDict(extra="ignore")
    fullname: str = ""


class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    text: str = ""
    timecreated: int = 0


class Conversation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    members: list[Member] = Field(default_factory=list)


class ConversationList(BaseModel):
    conversations: list[Conversation]


class MessageList(BaseModel):
    messages: list[Message]


class PersonalRecords:
    def __init__(self, service: Service) -> None:
        self.service = service

    def user_id(self) -> int:
        html = self.service.http.get("/my/courses.php").text()
        soup = BeautifulSoup(html, "html.parser")
        values = {str(node["data-userid"]) for node in soup.select("[data-userid]")}
        if len(values) != 1 or not next(iter(values)).isdigit():
            raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Cannot identify the signed-in user.")
        return int(next(iter(values)))

    def list(
        self,
        kind: Literal["grades", "feedback", "submissions", "messages"],
        course_id: int | None,
        query: str | None,
        offset: int,
        limit: int,
    ) -> dict[str, JsonValue]:
        if kind == "messages":
            if not query or not query.strip():
                raise MoodleError(
                    ErrorCode.ACCESS_DENIED, "Specify the person or conversation to find."
                )
            response = self.service.http.read_api(
                "core_message_get_conversations",
                {
                    "userid": self.user_id(),
                    "limitfrom": offset,
                    "limitnum": limit,
                },
            )
            conversations = ConversationList.model_validate(response).conversations
            records = [
                Material(
                    id=f"private:messages:{item.id}",
                    course_id=0,
                    kind="private_messages",
                    title=", ".join(member.fullname for member in item.members),
                    url=f"{BASE_URL}/message/index.php?id={item.id}",
                )
                for item in conversations
                if query.casefold()
                in " ".join(member.fullname for member in item.members).casefold()
            ]
            self.service.library.put_materials(records)
            return {
                "records": [item.model_dump(mode="json") for item in records],
                "next_cursor": str(offset + limit) if len(conversations) == limit else None,
                "coverage": "Only this page of accessible conversations was searched.",
            }
        if course_id is None:
            raise MoodleError(ErrorCode.ACCESS_DENIED, "Choose a current-semester course.")
        self.service.moodle.require_course(course_id)
        if kind == "grades":
            url = f"{BASE_URL}/grade/report/user/index.php?id={course_id}"
            html = self.service.http.get(url).text()
            soup = BeautifulSoup(html, "html.parser")
            if soup.select_one("table.user-grade, table.generaltable") is None:
                return {"records": [], "availability": "No readable grade report was found."}
            records = [
                Material(
                    id=f"private:grades:{course_id}",
                    course_id=course_id,
                    title="Your grade report",
                    kind="private_grades",
                    url=url,
                )
            ]
        else:
            assignments = [
                item for item in self.service.materials(course_id) if item.kind == "assign"
            ]
            records = [
                Material(
                    id=f"private:{kind}:{item.id.split(':')[1]}",
                    course_id=course_id,
                    title=item.title,
                    kind=f"private_{kind}",
                    url=item.url,
                )
                for item in assignments[offset : offset + limit]
            ]
        self.service.library.put_materials(records)
        return {"records": [item.model_dump(mode="json") for item in records]}

    def read(self, identity: str, cursor: str | None, limit: int) -> dict[str, JsonValue]:
        item = self.service.library.material(identity)
        if not item.kind.startswith("private_"):
            raise MoodleError(ErrorCode.ACCESS_DENIED, "Choose a previously listed own record.")
        if item.kind == "private_file":
            _, extracted, _ = self.service.read(identity)
            return {
                "record": item.model_dump(mode="json"),
                **excerpt(extracted, cursor, limit, None, None),
            }
        if item.kind == "private_messages":
            batch, inner = (cursor or "0|").split("|", 1) if "|" in (cursor or "0|") else ("", "")
            if not batch.isdigit() or len(batch) > 7:
                raise MoodleError(ErrorCode.RESOURCE_UNSUPPORTED, "Invalid message cursor.")
            offset = int(batch)
            response = self.service.http.read_api(
                "core_message_get_conversation_messages",
                {
                    "currentuserid": self.user_id(),
                    "convid": int(identity.rsplit(":", 1)[1]),
                    "limitfrom": offset,
                    "limitnum": 20,
                    "newest": False,
                },
            )
            messages = MessageList.model_validate(response).messages
            content = Extracted(
                pages=[
                    TextPage(number=message.id, text=main_text(message.text), unit="post")
                    for message in messages
                ]
            )
            result = excerpt(content, inner or None, limit, None, None)
            continuation = result["next_cursor"]
            result["next_cursor"] = (
                f"{batch}|{continuation}"
                if continuation
                else (f"{offset + 20}|" if len(messages) == 20 else None)
            )
            return {
                "record": item.model_dump(mode="json"),
                **result,
            }
        self.service.moodle.require_course(item.course_id)
        html = self.service.http.get(item.url).text()
        attachments: list[Material] = []
        soup = BeautifulSoup(html, "html.parser")
        for section in soup.select(".submissionstatustable, .fileuploadsubmission, .feedback"):
            attachments.extend(
                child.model_copy(update={"kind": "private_file", "id": "private:" + child.id})
                for child in files_from_html(str(section), item)
            )
        self.service.library.put_materials(attachments)
        text = main_text(html)
        return {
            "record": item.model_dump(mode="json"),
            "attachments": [attachment.model_dump(mode="json") for attachment in attachments],
            **excerpt(
                Extracted(pages=[TextPage(number=1, text=text, unit="section")]),
                cursor,
                limit,
                None,
                None,
            ),
        }

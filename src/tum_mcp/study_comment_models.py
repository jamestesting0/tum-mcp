"""Bounded, literal passage comments and optimistic local mutations."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StringConstraints, TypeAdapter, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_models import Digest, Key

NoteText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class Anchor(Frozen):
    view: Literal["content", "flashcards", "practice"] = "content"
    unit_key: Key
    unit_revision: Digest
    block_index: int = Field(default=0, ge=0, le=39)
    block_title: str = Field(min_length=1, max_length=10000)
    item_key: Key | None = None
    field: str | None = Field(default=None, min_length=1, max_length=100)
    quote: str = Field(min_length=1, max_length=2000)
    prefix: str = Field(default="", max_length=80)
    suffix: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def activity_target(self) -> "Anchor":
        if self.view == "content":
            if self.item_key is not None or self.field is not None:
                raise ValueError("Content comments use a section target.")
        elif self.item_key is None or self.field is None:
            raise ValueError("Activity comments require an item and field.")
        elif self.view == "flashcards" and self.field not in {"front", "back"}:
            raise ValueError("Unknown flashcard face.")
        elif self.view == "practice" and self.field not in {"prompt", "explanation", "correct"}:
            if not (
                self.field.startswith(("option:", "feedback:")) and self.field.split(":", 1)[1]
            ):
                raise ValueError("Unknown practice field.")
        return self


class ExerciseAnchor(Frozen):
    workspace: Literal["exercises"] = "exercises"
    view: Literal["exercises"] = "exercises"
    set_key: Key
    exercise_key: Key
    exercise_revision: Digest
    step_key: Key | None = None
    field: str = Field(min_length=1, max_length=100)
    block_title: str = Field(min_length=1, max_length=10000)
    quote: str = Field(min_length=1, max_length=2000)
    prefix: str = Field(default="", max_length=80)
    suffix: str = Field(default="", max_length=80)


class LectureAnchor(Frozen):
    view: Literal["lectures"] = "lectures"
    lecture_key: Key
    section_key: Key
    semantic_revision: Digest
    quote: str = Field(min_length=1, max_length=2000)
    prefix: str = Field(default="", max_length=80)
    suffix: str = Field(default="", max_length=80)


class Comment(Frozen):
    id: UUID
    anchor: Anchor | ExerciseAnchor | LectureAnchor
    text: NoteText
    status: Literal["open", "resolved"] = "open"
    resolution: str = Field(default="", max_length=2000)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Comments(Frozen):
    schema_version: Literal[1, 2, 3] = 1
    course_identity: Digest
    comments: tuple[Comment, ...] = Field(default=(), max_length=500)

    @model_validator(mode="after")
    def unique_ids(self) -> "Comments":
        if len({item.id for item in self.comments}) != len(self.comments):
            raise ValueError("Duplicate comment IDs.")
        return self


class Change(Frozen):
    course_identity: Digest
    expected_revision: Digest


class Create(Change):
    op: Literal["create"]
    id: UUID
    anchor: Anchor | ExerciseAnchor | LectureAnchor
    text: NoteText


class Edit(Change):
    op: Literal["edit"]
    id: UUID
    text: NoteText


class SetStatus(Change):
    op: Literal["status"]
    id: UUID
    status: Literal["open", "resolved"]
    resolution: str = Field(default="", max_length=2000)


class Delete(Change):
    op: Literal["delete"]
    id: UUID


Operation = Annotated[Create | Edit | SetStatus | Delete, Field(discriminator="op")]
OPERATION = TypeAdapter(Operation)

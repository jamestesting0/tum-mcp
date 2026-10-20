from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")


class Course(Model):
    id: int
    fullname: str
    shortname: str = ""
    startdate: int = 0
    enddate: int = 0
    viewurl: str = ""


class CoursePage(Model):
    courses: list[Course]
    nextoffset: int = 0


class Material(Model):
    id: str
    course_id: int
    title: str
    kind: str
    url: str
    section: str = ""
    parent_id: str = ""
    inline_text: str = ""


class TextPage(Model):
    number: int
    text: str
    unit: Literal["page", "slide", "section", "post"] = "page"


class Extracted(Model):
    pages: list[TextPage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Post(Model):
    id: str
    author: str
    text: str
    url: str
    parent_id: str = ""
    timestamp: str = ""
    attachments: list[Material] = Field(default_factory=list)


class SearchHit(Model):
    material_id: str
    title: str
    url: str
    number: int
    text: str

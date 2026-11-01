"""Optional reviewed course concepts and assertion-level source provenance."""

import json
import unicodedata
from typing import Annotated, Literal, assert_never

from pydantic import ConfigDict, Field, JsonValue, field_validator, model_validator

from tum_mcp.settings import Frozen
from tum_mcp.study_models import Digest, Key, PageRange
from tum_mcp.study_store import digest

_KEY = r"[a-z0-9][a-z0-9_.-]{0,99}"
_ITEM = (
    rf"^(study/unit/{_KEY}(/(block|question|flashcard)/{_KEY}|/explore/{_KEY}(/block/{_KEY})?)?"
    rf"|exercises/set/{_KEY}/exercise/{_KEY}(/step/{_KEY})?"
    rf"|exam/(concept/{_KEY}|pattern/{_KEY}|sitting/{_KEY}/variant/{_KEY}(/question/{_KEY})?"
    rf"|mock/{_KEY}(/question/{_KEY})?)"
    rf"|lectures/lecture/{_KEY}(/section/{_KEY})?)$"
)
ItemRef = Annotated[str, Field(pattern=_ITEM)]
Name = Annotated[str, Field(min_length=1, max_length=200)]
Purpose = Literal["study", "lectures", "exercises", "exam", "review"]
Relation = Literal["teaches", "practices", "assesses", "clarifies", "prerequisite_of", "contrasts"]


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def canonical_digest(value: JsonValue) -> str:
    return digest(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    )


class ConceptEndpoint(Frozen):
    kind: Literal["concept"]
    key: Key

    @property
    def node_id(self) -> str:
        return f"concept/{self.key}"


class ItemEndpoint(Frozen):
    kind: Literal["item"]
    ref: ItemRef

    @property
    def node_id(self) -> str:
        return self.ref


Endpoint = Annotated[ConceptEndpoint | ItemEndpoint, Field(discriminator="kind")]


class Concept(Frozen):
    key: Key
    label: Name
    aliases: tuple[Name, ...] = Field(default=(), max_length=32)
    summary: str = Field(default="", max_length=2000)

    @field_validator("label", "aliases")
    @classmethod
    def names(cls, value: str | tuple[str, ...]) -> str | tuple[str, ...]:
        match value:
            case str():
                values = (value,)
            case tuple():
                values = value
            case unreachable:
                assert_never(unreachable)
        names = [normalized(item) for item in values]
        if any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("Concept labels and aliases must be nonblank and distinct.")
        return value


class SourceEvidence(Frozen):
    kind: Literal["source"]
    source: Key
    sha256: Digest
    pages: PageRange | None = None

    @field_validator("pages")
    @classmethod
    def ordered_pages(cls, value: str | None) -> str | None:
        if value and "-" in value:
            first, last = value.split("-")
            if int(first) > int(last):
                raise ValueError("Evidence pages must be in increasing order.")
        return value


class LectureEvidence(Frozen):
    kind: Literal["lecture"]
    lecture: Key
    evidence: Key


Evidence = Annotated[SourceEvidence | LectureEvidence, Field(discriminator="kind")]


class SupportGroup(Frozen):
    key: Key
    evidence: tuple[Evidence, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def distinct_evidence(self) -> "SupportGroup":
        if len({item.model_dump_json() for item in self.evidence}) != len(self.evidence):
            raise ValueError("Repeated evidence is not independent support.")
        return self


class ReviewReceipt(Frozen):
    status: Literal["candidate", "reviewed", "rejected"] = "candidate"
    revision: Digest | None = None

    @model_validator(mode="after")
    def receipt(self) -> "ReviewReceipt":
        if (self.status == "reviewed") != (self.revision is not None):
            raise ValueError("Only reviewed assertions carry a review revision.")
        return self


class Assertion(Frozen):
    model_config = ConfigDict(serialize_by_alias=True)

    key: Key
    relation: Relation
    start: Endpoint = Field(alias="from")
    end: Endpoint = Field(alias="to")
    rationale: Annotated[str, Field(min_length=1, max_length=2000)]
    conditions: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(), max_length=16
    )
    support_groups: tuple[SupportGroup, ...] = Field(min_length=1, max_length=8)
    review: ReviewReceipt = Field(default_factory=ReviewReceipt)

    @model_validator(mode="before")
    @classmethod
    def symmetric_order(cls, value: JsonValue) -> JsonValue:
        match value:
            case {
                "relation": "contrasts",
                "from": {"kind": "concept", "key": str(a)} as left,
                "to": {"kind": "concept", "key": str(b)} as right,
            } if a > b:
                return value | {"from": right, "to": left}
            case _:
                return value

    @model_validator(mode="after")
    def endpoints(self) -> "Assertion":
        if self.start.node_id == self.end.node_id:
            raise ValueError("Assertions cannot relate an endpoint to itself.")
        match self.relation:
            case "prerequisite_of" | "contrasts":
                valid = isinstance(self.start, ConceptEndpoint) and isinstance(
                    self.end, ConceptEndpoint
                )
            case "teaches" | "practices" | "assesses" | "clarifies":
                valid = isinstance(self.start, ItemEndpoint) and isinstance(
                    self.end, ConceptEndpoint
                )
            case unreachable:
                assert_never(unreachable)
        if not valid:
            raise ValueError("Relation endpoints have incompatible kinds or direction.")
        if not self.rationale.strip() or any(not item.strip() for item in self.conditions):
            raise ValueError("Assertion rationale and conditions must be nonblank.")
        if len({group.key for group in self.support_groups}) != len(self.support_groups):
            raise ValueError("Support group keys must be unique within an assertion.")
        return self


class KnowledgeRegistry(Frozen):
    schema_version: Literal[1] = 1
    course_key: Key
    semester: Annotated[str, Field(min_length=1, max_length=100)]
    concepts: tuple[Concept, ...] = Field(default=(), max_length=2000)
    assertions: tuple[Assertion, ...] = Field(default=(), max_length=10000)

    @model_validator(mode="after")
    def identities(self) -> "KnowledgeRegistry":
        for records in (self.concepts, self.assertions):
            if len({item.key for item in records}) != len(records):
                raise ValueError("Concept and assertion keys must be unique in their collections.")
        signatures = [
            (a.relation, a.start.node_id, a.end.node_id, a.conditions) for a in self.assertions
        ]
        if len(set(signatures)) != len(signatures):
            raise ValueError("Combine equivalent assertion evidence into support groups.")
        return self

"""The course's term list: key terms in two languages and glosses for difficult words.

Authors list each term once in app/terms.json; the build marks its first use in each unit,
exercise, Exam context and lecture, so prose carries no markers or bracketed translations.
"""

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated

from pydantic import Field, JsonValue, ValidationError, model_validator

from tum_mcp.course.content.latex import INLINE_SPANS
from tum_mcp.course.content.study import LITERAL_FIELDS, TERM_MARKER, TERM_PROSE
from tum_mcp.course.project.paths import APP
from tum_mcp.course.project.store import Write, apply, confined, read_bytes
from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen

TERMS = f"{APP}/terms.json"
Form = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[^{}\r\n]+$")]
Language = Annotated[str, Field(pattern=r"^[a-z]{2}$")]


class Gloss(Frozen):
    term: Form
    meaning: Annotated[str, Field(min_length=1, max_length=240)]

    @model_validator(mode="after")
    def plain(self) -> "Gloss":
        if self.term != self.term.strip() or not self.meaning.strip() or "{{" in self.meaning:
            raise ValueError("A gloss needs a trimmed term and a plain meaning.")
        return self


class TermList(Frozen):
    # Each pair names one key term per language; a list adds inflected spellings after the
    # display form.
    pairs: tuple[dict[Language, Form | tuple[Form, ...]], ...] = Field(default=(), max_length=300)
    glosses: tuple[Gloss, ...] = Field(default=(), max_length=200)

    @model_validator(mode="after")
    def distinct(self) -> "TermList":
        for pair in self.pairs:
            if len(pair) < 2 or any(isinstance(v, tuple) and not v for v in pair.values()):
                raise ValueError("A pair names its term in at least two languages.")
        forms = [form for _, form in set(self.forms())]
        if len(set(forms)) != len(forms):
            raise ValueError("List each term form in one pair only.")
        glosses = [entry.term.lower() for entry in self.glosses]
        if len(set(glosses)) != len(glosses):
            raise ValueError("Gloss each term once.")
        return self

    def forms(self) -> Iterable[tuple[int, str]]:
        """Every pair form, lowercased, with its pair's index."""
        for index, pair in enumerate(self.pairs):
            for value in pair.values():
                for form in (value,) if isinstance(value, str) else value:
                    yield index, form.lower()

    def bubbles(self) -> dict[str, JsonValue]:
        """Each listed form with what its bubble shows: the term in its other languages and,
        for a glossed word, the meaning."""
        result: dict[str, dict[str, JsonValue]] = {}
        for pair in self.pairs:
            shown = {lang: _display(value) for lang, value in pair.items()}
            for lang, value in pair.items():
                for form in (value,) if isinstance(value, str) else value:
                    others = {
                        k: v for k, v in shown.items() if k != lang and v.lower() != form.lower()
                    }
                    if others:
                        result[form.lower()] = {"pair": others}
        for entry in self.glosses:
            result.setdefault(entry.term.lower(), {})["meaning"] = entry.meaning
        return dict(result)

    def marker(self) -> "Marker":
        return Marker(self)


class Marker:
    """Marks the first prose use of each listed term in one context at a time."""

    def __init__(self, terms: TermList) -> None:
        self.terms = terms
        self.groups: dict[str, frozenset[str]] = {}
        # A form spelled the same in every language has nothing to show.
        shown = terms.bubbles()
        for index, form in terms.forms():
            if form in shown:
                self.groups[form] = self.groups.get(form, frozenset()) | {f"pair:{index}"}
        for index, entry in enumerate(terms.glosses):
            key = entry.term.lower()
            self.groups[key] = self.groups.get(key, frozenset()) | {f"gloss:{index}"}
        names = sorted(self.groups, key=len, reverse=True)
        # Longest form first, whole words only; a hyphen joins a compound into one word.
        alternatives = "|".join(re.escape(name) for name in names) or "(?!)"
        self.pattern = re.compile(rf"(?<![\w-])({alternatives})(?![\w-])", re.IGNORECASE)
        self.used: set[str] = set()

    def mark(self, context: JsonValue) -> None:
        """Wrap the context's first use of each term in {{...}}, in place; existing markers
        count as uses."""
        if self.groups:
            self._walk(context, False, set())

    def _walk(self, value: JsonValue, prose: bool, seen: set[str]) -> None:
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    value[index] = self._text(item, seen) if prose else item
                else:
                    self._walk(item, prose, seen)
        elif isinstance(value, dict):
            for field, item in value.items():
                if field in LITERAL_FIELDS:
                    continue
                if isinstance(item, str):
                    value[field] = self._text(item, seen) if field in TERM_PROSE else item
                else:
                    self._walk(item, field in TERM_PROSE, seen)

    def _text(self, text: str, seen: set[str]) -> str:
        parts: list[str] = []
        start = 0
        # Inline code, inline math and existing markers stay as written.
        for span in re.finditer(f"{INLINE_SPANS.pattern}|{TERM_MARKER.pattern}", text, re.DOTALL):
            parts.append(self._plain(text[start : span.start()], seen))
            if span[0].startswith("{{"):
                _ = self._use(span[0][2:-2].strip().lower(), seen)
            parts.append(span[0])
            start = span.end()
        parts.append(self._plain(text[start:], seen))
        return "".join(parts)

    def _plain(self, text: str, seen: set[str]) -> str:

        def replace(match: re.Match[str]) -> str:
            return f"{{{{{match[1]}}}}}" if self._use(match[1].lower(), seen) else match[0]

        return self.pattern.sub(replace, text)

    def _use(self, form: str, seen: set[str]) -> bool:
        ids = self.groups.get(form, frozenset())
        if not ids or ids <= seen:
            return False
        seen |= ids
        self.used |= ids
        return True

    def unused(self) -> list[str]:
        """Listed terms that no context used, by display form."""
        # A pair spelled the same in every language has no bubble, so it is never marked.
        markable = {name for names in self.groups.values() for name in names}
        pairs = [
            _display(next(iter(pair.values())))
            for index, pair in enumerate(self.terms.pairs)
            if f"pair:{index}" in markable and f"pair:{index}" not in self.used
        ]
        glosses = [
            entry.term
            for index, entry in enumerate(self.terms.glosses)
            if f"gloss:{index}" not in self.used
        ]
        return pairs + glosses


def _display(value: str | tuple[str, ...]) -> str:
    return value if isinstance(value, str) else value[0]


def read_terms(root: Path) -> TermList:
    body = read_bytes(confined(root, TERMS))
    if body is None:
        return TermList()
    try:
        return TermList.model_validate_json(body)
    except ValidationError as error:
        details = [
            f"{'.'.join(map(str, item['loc'])) or 'top level'} "
            f"({item['msg'].removeprefix('Value error, ')})"
            for item in error.errors(include_input=False)
        ]
        raise CampusError(
            Code.INVALID_RESPONSE, f"Invalid {TERMS}: " + "; ".join(details[:5]) + "."
        ) from None


def move_annotations(root: Path, index: str) -> None:
    """Move Study's former annotations list into the course term list as glosses, once."""
    path = confined(root, index)
    before = read_bytes(path)
    if before is None:
        return
    try:
        document = json.loads(before)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return
    if not isinstance(document, dict) or "annotations" not in document:
        return
    legacy = document.pop("annotations") or []
    terms_before = read_bytes(confined(root, TERMS))
    current = json.loads(terms_before) if terms_before else {}
    known = {entry.get("term", "").lower() for entry in current.get("glosses", [])}
    current["glosses"] = [
        *current.get("glosses", []),
        *(entry for entry in legacy if entry.get("term", "").lower() not in known),
    ]

    def encode(value: dict) -> bytes:
        return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()

    apply(
        root,
        (
            Write(index, before, encode(document)),
            Write(TERMS, terms_before, encode(current)),
        ),
    )

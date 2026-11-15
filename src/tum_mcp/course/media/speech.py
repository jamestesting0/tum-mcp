"""Checks on sentences a voice reads aloud, shared by audio tracks and video narration."""

import re

from pydantic import JsonValue

# LaTeX, markup and symbols a voice reads as characters (or skips): say them in words.
UNSPEAKABLE = re.compile(r"\\[(\[a-zA-Z]|[_^{}$|]|[∑∏∫√≤≥≠≈→←↔⇒⇔∀∃¬∧∨⊨⊢∈∉⊂⊆∪∩×÷·∞]")
META = re.compile(
    r"\bprepared\b|\b(?:this|the) (?:track|audio(?: note)?s?|recording|episode|video)\b", re.I
)
PRONOUN_START = re.compile(r"^(?:this|that|these|those|it|they|he|she)\b", re.I)
LONG_WORDS = 40
# An outline marks every text the author still has to write; none may reach a student.
PLACEHOLDER = "Write:"


def unwritten(value: JsonValue, path: str = "") -> list[str]:
    if isinstance(value, str):
        return (
            [f"outline.unwritten {path}: replace the outline's placeholder"]
            if value.startswith(PLACEHOLDER)
            else []
        )
    if isinstance(value, dict):
        return [e for key, item in value.items() for e in unwritten(item, f"{path}.{key}")]
    if isinstance(value, list):
        return [e for i, item in enumerate(value) for e in unwritten(item, f"{path}[{i}]")]
    return []


def spoken(where: str, sentences: tuple[str, ...], *, opens: bool) -> tuple[list[str], list[str]]:
    """Errors and warnings for one chapter or beat; `opens` marks the first one a listener who
    skips there hears, which must name its subject."""
    errors: list[str] = []
    warnings: list[str] = []
    for index, sentence in enumerate(sentences, 1):
        if found := UNSPEAKABLE.search(sentence):
            errors.append(
                f"speech.symbols {where}/{index}: '{found[0]}' in '{sentence[:80]}'; "
                "say the mathematics in words"
            )
        if found := META.search(sentence):
            warnings.append(
                f"speech.meta {where}/{index}: '{found[0]}' talks about the material, "
                "not the subject"
            )
        if len(sentence.split()) > LONG_WORDS:
            warnings.append(f"speech.long {where}/{index}: split sentences over {LONG_WORDS} words")
    if opens and sentences and PRONOUN_START.search(sentences[0]):
        warnings.append(
            f"reentry.pronoun {where}: a chapter opens by naming its subject, "
            "so a listener who skips to it knows what 'it' is"
        )
    return errors, warnings

"""Copyable examples of what media authors write, each printed with its authoring rule."""

import json
from importlib.resources import files

from pydantic import BaseModel, JsonValue

from tum_mcp.errors import CampusError, Code


def _models() -> dict[str, dict[str, type[BaseModel]]]:
    from tum_mcp.course.media.audio_project import LeftToPage, ScriptChapter, SourceRef
    from tum_mcp.course.media.video_content import (
        Beat,
        ExerciseBeat,
        OnScreen,
        PageLeft,
        PatternBeat,
        SelectionFile,
    )

    return {
        "video": {
            "unit-beat": Beat,
            "exercise-beat": ExerciseBeat,
            "pattern-beat": PatternBeat,
            "on-screen": OnScreen,
            "left-to-page": PageLeft,
            "selection": SelectionFile,
        },
        "audio": {"chapter": ScriptChapter, "left-to-page": LeftToPage, "source": SourceRef},
    }


def catalogue(medium: str) -> dict[str, JsonValue]:
    data = json.loads((files("tum_mcp") / "bundled/exemplars/media.json").read_bytes())
    return data[medium]


def example(medium: str, name: str) -> tuple[str, JsonValue]:
    examples = catalogue(medium)
    if name not in examples:
        raise CampusError(Code.ACTION_REQUIRED, f"Unknown example {name}; use --example list.")
    model = _models()[medium][name]
    return " ".join((model.__doc__ or "").split()), examples[name]

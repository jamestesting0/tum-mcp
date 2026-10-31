"""Choose public workspaces before deriving sources, math and figure bytes."""

import json
from pathlib import Path

from pydantic import ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.lecture_assets import figure_bytes
from tum_mcp.lecture_evidence import Figure
from tum_mcp.study_build import _inline_math
from tum_mcp.study_figures import figure_bytes as study_figure_bytes
from tum_mcp.study_figures import figure_images


def project(data: bytes, *, include_exercises: bool, include_lectures: bool) -> dict:
    if not data.startswith(b"export default "):
        raise CampusError(
            Code.WORKSPACE_CONFLICT, "Rebuild generated study data before publishing."
        )
    try:
        payload = json.loads(data.removeprefix(b"export default ").removesuffix(b";\n"))
        if not include_exercises:
            payload.pop("exercises", None)
            payload.pop("pending", None)
        if not include_lectures:
            payload.pop("lectures", None)
        # Exam reproduces past exams and private uploads: it is never published.
        payload.pop("exam", None)
        payload["workspaces"] = (
            (["study"] if payload["units"] else [])
            + (["exercises"] if payload.get("exercises") else [])
            + (["lectures"] if payload.get("lectures") else [])
        )
        if not payload["workspaces"]:
            raise CampusError(
                Code.ACTION_REQUIRED,
                "Explicitly include Exercises or Lecture to publish this app.",
            )
        study_references = {s["key"] for unit in payload["units"] for s in unit["sources"]}
        study_references.update(
            source["key"]
            for unit in payload["units"]
            for item in unit.get("explore", [])
            for source in item["sources"]
        )
        references = set(study_references)
        if "studyPreparation" in payload:
            payload["studyPreparation"] = {
                "pending": [
                    entry
                    for entry in payload["studyPreparation"].get("pending", [])
                    if entry["source"] in study_references
                ]
            }
        references.update(
            s["key"]
            for group in payload.get("exercises", {}).get("sets", [])
            for exercise in group["exercises"]
            for s in exercise["sources"]
        )
        references.update(
            s["key"]
            for lecture in payload.get("lectures", {}).get("lectures", [])
            for s in lecture["sources"]
        )
        # Course files stay local: a published citation names its source but never its stored copy.
        payload["sources"] = {
            k: {field: value for field, value in v.items() if field != "file"}
            for k, v in payload["sources"].items()
            if k in references
        }
        payload["inlineMath"] = _inline_math(
            [
                payload["introduction"],
                payload["units"],
                payload.get("exercises"),
                payload.get("lectures"),
            ]
        )
    except (KeyError, TypeError, ValueError):
        raise CampusError(Code.WORKSPACE_CONFLICT, "Rebuild the generated site data.") from None
    return payload


def assets(root: Path, payload: dict) -> dict[str, bytes]:
    result = {
        image: study_figure_bytes(app_path(root, image))
        for image in set(figure_images([payload.get("units"), payload.get("exercises")]))
    }
    try:
        for lecture in payload.get("lectures", {}).get("lectures", []):
            for section in lecture["sections"]:
                for item in section["figures"]:
                    figure = Figure.model_validate(
                        {key: value for key, value in item.items() if key in Figure.model_fields}
                    )
                    result[figure.asset] = figure_bytes(app_path(root, figure.asset), figure)
    except (KeyError, TypeError, ValidationError):
        raise CampusError(
            Code.INVALID_RESPONSE, "Rebuild selected lecture figures before publishing."
        ) from None
    return result

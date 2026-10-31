"""Read a course once and detect changes to the local evidence observed by a request."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, JsonValue, ValidationError

from tum_mcp.course_app_paths import app_path
from tum_mcp.errors import CampusError, Code
from tum_mcp.exam_content import ExamContent
from tum_mcp.exercise_content import ExerciseContent
from tum_mcp.extension_selection import require_course_memory
from tum_mcp.lecture_content import LectureContent
from tum_mcp.study_content import StudyContent
from tum_mcp.study_coverage import CoverageLedger
from tum_mcp.study_knowledge_models import KnowledgeRegistry, canonical_digest
from tum_mcp.study_models import ResourceState, StudyState
from tum_mcp.study_store import confined, digest, private_path


@dataclass(frozen=True, slots=True)
class Observation:
    sha256: str | None
    limit: int


@dataclass(slots=True)
class SnapshotReader:
    """Request-local accumulator; new reads extend the set verified before returning."""

    root: Path
    observations: dict[Path, Observation] = field(default_factory=dict)

    def observe(self, path: Path, body: bytes | None) -> None:
        self.record(
            path,
            Observation(
                digest(body) if body is not None else None, max(len(body or b""), 8 * 1024**2)
            ),
        )

    def record(self, path: Path, observation: Observation) -> None:
        if path in self.observations and self.observations[path].sha256 != observation.sha256:
            raise CampusError(Code.STALE_RESULT, "Course inputs changed during this request.")
        self.observations[path] = observation

    def read(self, path: Path) -> bytes | None:
        confined(self.root, path.relative_to(self.root).as_posix())
        try:
            if not path.exists():
                self.observe(path, None)
                return None
            if not path.is_file() or path.stat().st_size > 8 * 1024**2:
                raise CampusError(
                    Code.INVALID_RESPONSE, "Course metadata must be a file below 8 MiB."
                )
            with path.open("rb") as stream:
                body = stream.read(8 * 1024**2 + 1)
            if len(body) > 8 * 1024**2:
                raise CampusError(Code.INVALID_RESPONSE, "Course metadata exceeds 8 MiB.")
        except OSError:
            raise CampusError(Code.INVALID_RESPONSE, "Course metadata could not be read.") from None
        self.observe(path, body)
        return body

    def fingerprint(self, path: Path, limit: int) -> str | None:
        confined(self.root, path.relative_to(self.root).as_posix())
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_size > limit:
            raise CampusError(Code.INVALID_RESPONSE, "Course evidence is occupied or oversized.")
        result = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024**2):
                size += len(chunk)
                if size > limit:
                    raise CampusError(
                        Code.INVALID_RESPONSE, "Course evidence grew beyond its bound."
                    )
                result.update(chunk)
        return result.hexdigest()

    def verify(self) -> str:
        private_path(self.root, "state.json")
        app_path(self.root, "content.json")
        for path, observation in self.observations.items():
            try:
                current = self.fingerprint(path, observation.limit)
            except CampusError as error:
                if error.code != Code.INVALID_RESPONSE:
                    raise
                raise CampusError(
                    Code.STALE_RESULT, "Observed course evidence changed its shape or size."
                ) from None
            except OSError:
                raise CampusError(
                    Code.STALE_RESULT, "Observed course evidence became unreadable."
                ) from None
            if current != observation.sha256:
                raise CampusError(
                    Code.STALE_RESULT, "Course inputs changed; request fresh context."
                )
        values: JsonValue = {
            path.relative_to(self.root).as_posix(): record.sha256
            for path, record in self.observations.items()
        }
        return canonical_digest(values)


@dataclass(frozen=True, slots=True)
class CourseInputs:
    root: Path
    reader: SnapshotReader
    state: StudyState
    study: StudyContent | None
    exercises: ExerciseContent | None
    exam: ExamContent | None
    lectures: LectureContent | None
    ledger: CoverageLedger | None
    registry: KnowledgeRegistry | None

    @property
    def resources(self) -> dict[str, ResourceState]:
        return {item.resource.key: item for item in self.state.resources}

    @property
    def workspaces(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, model in (
                ("study", self.study),
                ("exercises", self.exercises),
                ("exam", self.exam),
                ("lectures", self.lectures),
            )
            if model is not None
        )


def _model[T: BaseModel](reader: SnapshotReader, path: Path, model: type[T]) -> T | None:
    body = reader.read(path)
    if body is None:
        return None
    try:
        return model.model_validate_json(body)
    except ValidationError as error:
        names: set[str] = set()

        def fields(schema: JsonValue) -> None:
            if isinstance(schema, dict):
                names.update(schema.get("properties", {}))
                if isinstance(schema.get("const"), str):
                    names.add(schema["const"])
                for value in schema.values():
                    fields(value)
            elif isinstance(schema, list):
                for value in schema:
                    fields(value)

        fields(model.model_json_schema())
        locations = [
            ".".join(
                str(part) if isinstance(part, int) or part in names else "<field>"
                for part in item["loc"]
            )[:250]
            for item in error.errors(include_input=False)
        ]
        raise CampusError(
            Code.INVALID_RESPONSE, f"Invalid {path.name} at: {', '.join(locations[:5])}."
        ) from None


def load_inputs(project: Path) -> CourseInputs:
    require_course_memory()
    root = project.expanduser().resolve()
    reader = SnapshotReader(root)
    state = _model(reader, private_path(root, "state.json"), StudyState)
    if state is None:
        raise CampusError(Code.ACTION_REQUIRED, "Initialize one course with study init first.")
    result = CourseInputs(
        root,
        reader,
        state,
        _model(reader, app_path(root, "content.json"), StudyContent),
        _model(reader, app_path(root, "exercises.json"), ExerciseContent),
        _model(reader, app_path(root, "exam.json"), ExamContent),
        _model(reader, app_path(root, "lectures.json"), LectureContent),
        _model(reader, private_path(root, "coverage.json"), CoverageLedger),
        _model(reader, private_path(root, "knowledge.json"), KnowledgeRegistry),
    )
    for model in (
        result.study,
        result.exercises,
        result.exam,
        result.lectures,
        result.ledger,
        result.registry,
    ):
        if model is not None and model.course_key != state.course.key:
            raise CampusError(Code.SCOPE_DENIED, "Course content belongs to another course.")
    if result.registry is not None and result.registry.semester != state.course.semester:
        raise CampusError(Code.SCOPE_DENIED, "Knowledge annotations belong to another semester.")
    if result.lectures and any(
        item.recording.synthetic != state.course.synthetic for item in result.lectures.lectures
    ):
        raise CampusError(Code.SCOPE_DENIED, "Synthetic and real lecture evidence cannot be mixed.")
    return result

"""Student-facing Artemis response projections; secrets and staff fields are dropped."""

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel, SecretStr

from tum_mcp.settings import Frozen, PositiveId


class Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class Reference(Wire):
    id: PositiveId
    title: str = ""


class Identity(Wire):
    id: PositiveId
    login: str


class Courses(RootModel[tuple[Reference, ...]]):
    pass


class CourseDirectory(Frozen):
    account_id: str
    courses: tuple[Reference, ...]


class Feedback(Wire):
    id: int | None = None
    text: str | None = Field(default=None, max_length=10000)
    detail_text: str | None = Field(default=None, alias="detailText", max_length=30000)
    positive: bool | None = None


class Feedbacks(RootModel[tuple[Feedback, ...]]):
    pass


class Result(Wire):
    id: PositiveId
    completion_date: AwareDatetime | None = Field(default=None, alias="completionDate")
    successful: bool | None = None
    score: float | None = None
    feedbacks: tuple[Feedback, ...] | None = None


class Submission(Wire):
    id: PositiveId
    commit_hash: str | None = Field(default=None, alias="commitHash")
    build_failed: bool | None = Field(default=None, alias="buildFailed")
    results: tuple[Result, ...] | None = None


class SubmissionPolicy(Wire):
    type: str
    submission_limit: int | None = Field(default=None, alias="submissionLimit", ge=0)
    exceeding_penalty: float | None = Field(default=None, alias="exceedingPenalty", ge=0)
    active: bool | None = None


class Participation(Wire):
    id: PositiveId
    test_run: bool = Field(default=False, alias="testRun")
    repository_uri: SecretStr | None = Field(
        default=None, alias="repositoryUri", repr=False, exclude=True
    )
    branch: str | None = None
    individual_due_date: AwareDatetime | None = Field(default=None, alias="individualDueDate")
    exercise: Reference | None = None
    submissions: tuple[Submission, ...] | None = None
    submission_count: int | None = Field(default=None, alias="submissionCount", ge=0)


class Exercise(Wire):
    id: PositiveId
    title: str
    type: str
    course: Reference | None = None
    release_date: AwareDatetime | None = Field(default=None, alias="releaseDate")
    due_date: AwareDatetime | None = Field(default=None, alias="dueDate")
    exercise_group: Reference | None = Field(default=None, alias="exerciseGroup")
    problem_statement: str | None = Field(default=None, alias="problemStatement", max_length=100000)
    allow_offline_ide: bool | None = Field(default=None, alias="allowOfflineIde")
    mode: str | None = None
    submission_policy: SubmissionPolicy | None = Field(default=None, alias="submissionPolicy")
    student_participations: tuple[Participation, ...] | None = Field(
        default=None, alias="studentParticipations"
    )


class Overview(Wire):
    exercises: tuple[Exercise, ...]


class Details(Wire):
    exercise: Exercise


class ExerciseView(Frozen):
    account_id: str
    instance_id: str
    course_id: int
    exercise: Exercise
    fetched_at: float
    source_link: str
    untrusted_content: bool = True


class FeedbackView(Frozen):
    account_id: str
    participation_id: int
    commit_hash: str
    submission_id: int
    state: str
    results: tuple[Result, ...]
    fetched_at: float
    limitations: tuple[str, ...]

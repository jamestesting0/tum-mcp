from pathlib import Path
from uuid import uuid4

from tum_mcp.study_build import read_content, unit_revision
from tum_mcp.study_comment_models import Anchor, Create
from tum_mcp.study_comments import read_comments


def operation(project: Path) -> Create:
    current = read_comments(project)
    unit = read_content(project).units[0]
    return Create(
        op="create",
        id=uuid4(),
        course_identity=current["course_identity"],
        expected_revision=current["revision"],
        text="Explain this more clearly. <script>literal</script>",
        anchor=Anchor(
            unit_key=unit.key,
            unit_revision=unit_revision(unit),
            block_index=0,
            block_title=unit.blocks[0].title,
            quote="A graph",
            suffix=" has",
        ),
    )

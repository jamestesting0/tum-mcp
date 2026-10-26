from pathlib import Path

import anyio
import pytest
from mcp.server.mcpserver.exceptions import ToolError

from tum_mcp.credentials import Credential, Vault
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.courses import Course, CoursePage
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope

ACCOUNT = "a" * 64


def test_tumonline_tools_use_local_scope_and_bounded_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    account = AccountRef(account_id=ACCOUNT)
    credential = Credential(
        account_id=ACCOUNT,
        authentication="browser_session",
        cookies=(Cookie(name="session", value="synthetic-secret", domain="campus.tum.de"),),
    )
    Vault().save(account, credential)
    from tum_mcp.tumonline import server as online

    course = Course(
        id=1,
        number="IN1",
        title="Synthetic",
        term="2026 W",
        kind="VO",
        source_link="https://campus.tum.de/tumonline/ee/ui/ca2/app/desktop/#/slc.tm.cp/student/courses/1",
    )

    class FakeCourses:
        def __init__(self, policies):
            self.policies = policies

        def list(self, account_id, *, offset, limit):
            assert account_id == ACCOUNT and limit == 1
            return CoursePage(courses=(course,), coverage_status="partial", next_offset=offset + 1)

    monkeypatch.setattr(online, "PublicCourses", FakeCourses)

    async def exercise() -> None:
        result = await online.server.call_tool(
            "tumonline_list_courses", {"account_id": ACCOUNT, "limit": 1}
        )
        assert not result.is_error
        data = result.structured_content
        assert data["courses"][0]["title"] == "Synthetic"
        assert data["next_cursor"]
        assert "synthetic-secret" not in str(data)
        cursor = data["next_cursor"]
        policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
        with pytest.raises(ToolError):
            await online.server.call_tool(
                "tumonline_list_courses", {"account_id": ACCOUNT, "limit": 1, "cursor": cursor}
            )

    anyio.run(exercise)


def test_study_tool_exposes_minimal_names_and_respects_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    from tum_mcp.tumonline import server as online
    from tum_mcp.tumonline.studies import Study

    class FakeStudies:
        def __init__(self):
            pass

        def list(self, account_id):
            assert account_id == ACCOUNT
            return (Study(name="Synthetic degree", degree="Bachelor"),)

    monkeypatch.setattr(online, "StudyService", FakeStudies)

    async def exercise() -> None:
        result = await online.server.call_tool("tumonline_list_studies", {"account_id": ACCOUNT})
        assert not result.is_error
        assert result.structured_content["studies"][0]["name"] == "Synthetic degree"
        assert result.structured_content["coverage_status"] == "unknown"
        policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
        with pytest.raises(ToolError):
            await online.server.call_tool("tumonline_list_studies", {"account_id": ACCOUNT})

    anyio.run(exercise)


def test_curriculum_continuation_is_bound_to_course_and_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tum_mcp.tumonline import server as online
    from tum_mcp.tumonline.curriculum import CurriculumPosition, PositionPage

    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    policies = PolicyStore()
    policies.create(ACCOUNT)
    calls = []

    class FakeCurriculum:
        def __init__(self, policies):
            pass

        def list(self, account_id, course_id, *, offset, limit):
            calls.append((course_id, offset))
            return PositionPage(
                positions=(
                    CurriculumPosition(program="Synthetic", version="2024", path=("Module",)),
                ),
                next_offset=1 if offset == 0 else None,
            )

    monkeypatch.setattr(online, "PublicCurriculum", FakeCurriculum)

    async def exercise() -> None:
        page = await online.server.call_tool(
            "tumonline_course_curriculum", {"account_id": ACCOUNT, "course_id": 1, "limit": 1}
        )
        assert not page.is_error and page.structured_content["coverage_status"] == "partial"
        token = page.structured_content["next_cursor"]
        with pytest.raises(ToolError):
            await online.server.call_tool(
                "tumonline_course_curriculum",
                {
                    "account_id": ACCOUNT,
                    "course_id": 2,
                    "limit": 1,
                    "cursor": token,
                },
            )
        assert calls == [(1, 0)]
        policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
        with pytest.raises(ToolError):
            await online.server.call_tool(
                "tumonline_course_curriculum",
                {
                    "account_id": ACCOUNT,
                    "course_id": 1,
                    "limit": 1,
                    "cursor": token,
                },
            )
        assert calls == [(1, 0)]

    anyio.run(exercise)

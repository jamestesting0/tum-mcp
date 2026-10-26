"""Exercise bounded, on-demand retrieval through the MCP tool interface."""

import json
from pathlib import Path

import anyio
import httpx2
import pytest

from tum_mcp.credentials import Credential, Vault
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore
from tum_mcp.tumonline.transport import PublicCourses

ACCOUNT = "a" * 64


def test_catalog_pages_are_fetched_only_on_demand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TUM_MCP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("TUM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    PolicyStore().create(ACCOUNT)
    Vault().save(
        AccountRef(account_id=ACCOUNT),
        Credential(
            account_id=ACCOUNT,
            authentication="browser_session",
            cookies=(Cookie(name="session", value="synthetic", domain="campus.tum.de"),),
        ),
    )
    from tum_mcp.tumonline import server as online

    requests: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        offset = int(request.url.params["$skip"])
        requests.append(offset)
        return httpx2.Response(
            200,
            json={
                "totalCount": 2,
                "courses": [
                    {
                        "id": offset + 1,
                        "courseNumber": {"databaseValue": f"IN{offset}"},
                        "courseTitle": {"value": f"Synthetic course {offset}"},
                        "semesterDto": {"semesterDesignation": {"value": "2026 W"}},
                        "courseTypeDto": {"courseTypeShortName": {"value": "VO"}},
                        "grade": "private-synthetic-grade",
                    }
                ],
            },
        )

    transport = httpx2.MockTransport(handler)
    monkeypatch.setattr(
        online, "PublicCourses", lambda policies: PublicCourses(policies, transport)
    )

    async def exercise() -> None:
        first = await online.server.call_tool(
            "tumonline_list_courses", {"account_id": ACCOUNT, "limit": 1}
        )
        assert not first.is_error
        assert requests == [0]
        first_data = first.structured_content
        first_bytes = len(json.dumps(first_data).encode("utf-8"))
        assert first_bytes < 2_000
        assert first_data["coverage_status"] == "partial"
        assert "private-synthetic-grade" not in json.dumps(first_data)
        second = await online.server.call_tool(
            "tumonline_list_courses",
            {"account_id": ACCOUNT, "limit": 1, "cursor": first_data["next_cursor"]},
        )
        assert not second.is_error
        assert requests == [0, 1]
        assert second.structured_content["coverage_status"] == "complete"

    anyio.run(exercise)

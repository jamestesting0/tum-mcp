import json

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.tumonline.studies import project_studies


def test_study_projection_drops_progress_identifiers_and_arbitrary_links() -> None:
    body = json.dumps(
        {
            "resource": [
                {
                    "content": {
                        "CmStudyInfoDto": {
                            "studyId": 11,
                            "name": {"value": "Synthetic degree"},
                            "intendedDegree": {"value": "Bachelor"},
                            "myStudyLink": {"href": "https://example.invalid/private"},
                            "studyStatus": "synthetic-private-status",
                            "grade": "synthetic-private-grade",
                        }
                    }
                }
            ]
        }
    ).encode()
    result = project_studies(body)
    assert result[0].name == "Synthetic degree"
    assert result[0].degree == "Bachelor"
    encoded = result[0].model_dump_json()
    assert "synthetic-private" not in encoded
    assert "example.invalid" not in encoded
    assert "studyId" not in encoded


def test_study_projection_rejects_schema_changes() -> None:
    with pytest.raises(CampusError):
        project_studies(b'{"resource": [{"content": {}}]}')

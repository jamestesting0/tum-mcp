import json

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.tumonline.exams import OFFERS, read_offers

OFFER = {
    "id": 5,
    "courseName": {"value": "Synthetic Linear Algebra"},
    "displayCourseNumber": "MA0001",
    "courseSemesterShortName": {"value": "2026 W"},
    "examType": {"value": "Written exam"},
    "examDate": {"value": "2027-02-12"},
    "examStart": {"value": "09:00:00"},
    "appointments": [{"id": 1, "displayName": "Synthetic hall (0000.00.001)"}],
    "registrationDateStart": {"value": "2026-12-01T00:00:00"},
    "registrationDateEnd": {"value": "2027-01-15T23:59:59"},
    "deRegistrationEnd": {"value": "2027-02-05T23:59:59"},
    "registrationState": "NOT_REGISTERED",
    "examPersons": [{"identities": [{"firstName": "synthetic-private-examiner"}]}],
    "courseLink": {"href": "https://example.invalid/private"},
}


def test_offer_page_sends_paired_bounds_and_search_and_drops_examiners() -> None:
    calls = []

    def get(path, params=None):
        calls.append((path, params))
        return json.dumps({"examOffers": [OFFER], "totalCount": 3}).encode()

    page = read_offers(get, offset=0, limit=1, query="Linear")
    assert calls == [(OFFERS, {"$skip": "0", "$top": "1", "$filter": "q-likeI=Linear"})]
    (exam,) = page.exams
    assert (exam.course, exam.date, exam.start, exam.rooms) == (
        "Synthetic Linear Algebra",
        "2027-02-12",
        "09:00:00",
        ("Synthetic hall (0000.00.001)",),
    )
    assert exam.registration_end == "2027-01-15T23:59:59"
    assert (page.coverage_status, page.next_offset) == ("partial", 1)
    encoded = exam.model_dump_json()
    assert "synthetic-private" not in encoded and "example.invalid" not in encoded


def test_offer_page_rejects_more_offers_than_requested() -> None:
    def get(path, params=None):
        return json.dumps({"examOffers": [OFFER, OFFER], "totalCount": 4028}).encode()

    with pytest.raises(CampusError, match="INVALID_RESPONSE"):
        read_offers(get, offset=0, limit=1, query=None)

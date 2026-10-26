import pytest

from tum_mcp.errors import CampusError
from tum_mcp.tumonline.cursor import CursorBinding, CursorCodec

ACCOUNT = "a" * 64


def test_cursor_binds_account_limit_policy_and_expiry() -> None:
    codec = CursorCodec(b"synthetic-key")
    binding = CursorBinding(account_id=ACCOUNT, revision=3, limit=20)
    token = codec.encode(binding, offset=20, now=1000)
    assert codec.decode(token, binding, now=1001) == 20
    for wrong in (
        CursorBinding(account_id="b" * 64, revision=3, limit=20),
        CursorBinding(account_id=ACCOUNT, revision=4, limit=20),
        CursorBinding(account_id=ACCOUNT, revision=3, limit=10),
        CursorBinding(
            account_id=ACCOUNT,
            revision=3,
            limit=20,
            operation="curriculum_positions",
            course_id=1,
        ),
    ):
        with pytest.raises(CampusError):
            codec.decode(token, wrong, now=1001)
    with pytest.raises(CampusError):
        codec.decode(token, binding, now=9999)


def test_cursor_tampering_and_oversized_values_are_rejected() -> None:
    codec = CursorCodec(b"synthetic-key")
    binding = CursorBinding(account_id=ACCOUNT, revision=0, limit=20)
    token = codec.encode(binding, offset=20, now=1000)
    for invalid in (token[:-1] + "!", "x" * 1000):
        with pytest.raises(CampusError):
            codec.decode(invalid, binding, now=1001)

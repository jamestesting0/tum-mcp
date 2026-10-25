import os
from uuid import uuid4

import pytest

from tum_mcp.moodle.auth import system_keyring


def test_native_credential_store_round_trip() -> None:
    if os.environ.get("TUM_MOODLE_SYSTEM_KEYRING") != "1":
        pytest.skip("Set TUM_MOODLE_SYSTEM_KEYRING=1 to test the native desktop credential store.")
    backend = system_keyring()
    service = "tum-moodle-test-" + uuid4().hex
    value = uuid4().hex

    backend.set_password(service, "test-account", value)
    try:
        assert backend.get_password(service, "test-account") == value
    finally:
        backend.delete_password(service, "test-account")

    assert backend.get_password(service, "test-account") is None

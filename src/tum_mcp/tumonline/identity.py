"""Opaque account references derived from the verified TUMonline subject."""

import hashlib

from pydantic import Field

from tum_mcp.errors import CampusError, Code
from tum_mcp.settings import Frozen


class AccountRef(Frozen):
    account_id: str = Field(pattern=r"^[a-f0-9]{64}$")

    @property
    def id(self) -> str:
        return self.account_id


def account_for_subject(subject: str) -> AccountRef:
    """Derive an opaque local identity from a subject verified by TUMonline."""
    if not subject or len(subject) > 512:
        raise CampusError(Code.AUTH_REQUIRED, "TUMonline did not provide an account identity.")
    value = f"tumonline\0https://campus.tum.de\0{subject}".encode()
    return AccountRef(account_id=hashlib.sha256(value).hexdigest())

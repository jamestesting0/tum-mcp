"""Bounded public course catalog reads under the TUMonline policy."""

import logging
import socket
from typing import Final

import httpx2
from pydantic import ValidationError

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.tumonline.courses import CoursePage, search_query
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope

COURSES_URL: Final = "https://campus.tum.de/tumonline/ee/rest/slc.tm.cp/student/courses"
MAX_RESPONSE: Final = 2 * 1024 * 1024


def permitted_credential(vault: Vault, account: AccountRef) -> Credential:
    """Require an encrypted session with only secure TUMonline cookies."""
    credential = vault.load(account)
    if (
        credential.authentication != "browser_session"
        or not credential.cookies
        or any(c.domain.lstrip(".") != "campus.tum.de" or not c.secure for c in credential.cookies)
    ):
        raise CampusError(Code.AUTH_REQUIRED, "Reconnect the TUMonline account.")
    return credential


class PublicCourses:
    """Read a single anonymous course page under the account's local study scope."""

    def __init__(
        self,
        policies: PolicyStore,
        transport: httpx2.BaseTransport | None = None,
        *,
        vault: Vault | None = None,
    ) -> None:
        self.policies = policies
        self.transport = transport
        self.vault = vault

    def list(
        self, account_id: str, *, offset: int = 0, limit: int = 20, query: str | None = None
    ) -> CoursePage:
        if offset < 0 or not 1 <= limit <= 100:
            raise CampusError(Code.SCOPE_DENIED, "Invalid course page bounds.")
        query = search_query(query)
        policy = self.policies.read(account_id)
        if not policy.allows(Scope.STUDIES_COURSES):
            raise CampusError(Code.SCOPE_DENIED, "TUMonline studies and courses are disabled.")
        account = AccountRef(account_id=account_id)
        vault = self.vault or Vault()
        credential = permitted_credential(vault, account)
        if self.policies.read(account_id) != policy:
            raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
        transport = self.transport or httpx2.HTTPTransport(
            http2=True,
            retries=0,
            limits=httpx2.Limits(max_connections=4, max_keepalive_connections=2),
            socket_options=[(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)],
        )
        logging.getLogger("httpx2").setLevel(logging.WARNING)
        try:
            with httpx2.Client(
                transport=transport,
                timeout=httpx2.Timeout(20, connect=5),
                follow_redirects=False,
                headers={"Accept": "application/json"},
            ) as client:
                params = {"$top": str(limit), "$skip": str(offset)}
                if query is not None:
                    params["$filter"] = "filterTerm-like=" + query
                with client.stream("GET", COURSES_URL, params=params) as response:
                    if response.status_code in {401, 403}:
                        raise CampusError(Code.AUTH_REQUIRED, "TUMonline denied the request.")
                    if response.status_code == 429:
                        raise CampusError(Code.RATE_LIMITED, "TUMonline rate limit; retry later.")
                    if not response.is_success or response.is_redirect:
                        raise CampusError(Code.CAPABILITY_UNSUPPORTED, "TUMonline read failed.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if len(body) + len(chunk) > MAX_RESPONSE:
                            raise CampusError(
                                Code.INVALID_RESPONSE, "TUMonline response too large."
                            )
                        body.extend(chunk)
        except httpx2.HTTPError:
            raise CampusError(Code.OFFLINE, "TUMonline request failed.") from None
        try:
            result = CoursePage.from_wire(bytes(body), offset=offset, limit=limit)
        except ValidationError:
            raise CampusError(Code.INVALID_RESPONSE, "Invalid TUMonline course response.") from None
        if self.policies.read(account_id) != policy:
            raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")
        if vault.load(account).generation != credential.generation:
            raise CampusError(Code.STALE_RESULT, "TUMonline session changed; retry.")
        return result

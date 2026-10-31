"""Read the account's own TUMonline records under the scope that covers them."""

from collections.abc import Callable
from typing import cast

import httpx2

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.auth import STUDIES, Get, IdentityMismatch, resume_session
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.tumonline.studies import Study, project_studies


def read_personal[T](
    account_id: str,
    scope: Scope,
    read: Callable[[Get], T],
    transport: httpx2.BaseTransport | None = None,
) -> T:
    """Refresh the verified session and run `read` while `scope` stays allowed."""
    policies = PolicyStore()
    policy = policies.read(account_id)
    policy.require(scope)
    account = AccountRef(account_id=account_id)
    vault = Vault()

    def authorize() -> None:
        if policies.read(account_id) != policy:
            raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")

    def refresh(
        credential: Credential, checkpoint: Callable[[tuple[Cookie, ...]], None]
    ) -> tuple[tuple[Cookie, ...], T]:
        try:
            session, result = resume_session(
                credential.cookies,
                transport,
                expected=account,
                read=read,
                authorize=authorize,
                checkpoint_cookies=checkpoint,
            )
        except IdentityMismatch:
            checkpoint(credential.cookies)
            raise
        return session.cookies, cast(T, result)

    authorize()
    credential, result = vault.refresh_browser_session(account, refresh)
    authorize()
    if vault.load(account).generation != credential.generation:
        raise CampusError(Code.STALE_RESULT, "TUMonline session changed; retry.")
    return result


class StudyService:
    def __init__(self, transport: httpx2.BaseTransport | None = None) -> None:
        self.transport = transport

    def list(self, account_id: str) -> tuple[Study, ...]:
        body = read_personal(
            account_id, Scope.STUDIES_COURSES, lambda get: get(STUDIES), self.transport
        )
        return project_studies(body)

    def verify(self, account_id: str) -> None:
        """Verify identity without retrieving studies, grades or course content."""
        read_personal(account_id, Scope.STUDIES_COURSES, lambda get: None, self.transport)

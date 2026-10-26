"""Read the account's own study names under the TUMonline study scope."""

from collections.abc import Callable

import httpx2

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.auth import Cookie
from tum_mcp.tumonline.auth import IdentityMismatch, ResumedSession, resume_session
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore, Scope
from tum_mcp.tumonline.studies import Study, project_studies


class StudyService:
    def __init__(self, transport: httpx2.BaseTransport | None = None) -> None:
        self.transport = transport

    def list(self, account_id: str) -> tuple[Study, ...]:
        policies = PolicyStore()
        policy = policies.read(account_id)
        if not policy.allows(Scope.STUDIES_COURSES):
            raise CampusError(Code.SCOPE_DENIED, "TUMonline studies and courses are disabled.")
        account = AccountRef(account_id=account_id)
        vault = Vault()

        def authorize() -> None:
            if policies.read(account_id) != policy:
                raise CampusError(Code.STALE_RESULT, "TUMonline permissions changed; retry.")

        def refresh(
            credential: Credential, checkpoint: Callable[[tuple[Cookie, ...]], None]
        ) -> tuple[tuple[Cookie, ...], ResumedSession]:
            try:
                session = resume_session(
                    credential.cookies,
                    self.transport,
                    expected=account,
                    authorize=authorize,
                    checkpoint_cookies=checkpoint,
                )
            except IdentityMismatch:
                checkpoint(credential.cookies)
                raise
            return session.cookies, session

        authorize()
        credential, session = vault.refresh_browser_session(account, refresh)
        studies = project_studies(session.studies)
        authorize()
        if vault.load(account).generation != credential.generation:
            raise CampusError(Code.STALE_RESULT, "TUMonline session changed; retry.")
        return studies

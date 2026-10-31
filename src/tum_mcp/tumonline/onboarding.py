"""Store a verified TUMonline connection without resetting its local policy."""

from uuid import uuid4

from filelock import FileLock
from playwright.sync_api import BrowserContext

from tum_mcp.credentials import Credential, Vault
from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.tumonline.auth import ResumedSession
from tum_mcp.tumonline.identity import AccountRef
from tum_mcp.tumonline.policy import PolicyStore


def begin_login() -> str:
    """Create a generation that disconnect or a newer login can invalidate."""
    policies = PolicyStore()
    with FileLock(str(policies.root / "connect.lock")):
        marker = policies.root / "login-generation"
        if marker.is_symlink():
            raise CampusError(Code.SCOPE_DENIED, "TUMonline login marker cannot be a symlink.")
        attempt = uuid4().hex
        private_write(marker, attempt.encode())
        return attempt


def disconnect(account: AccountRef) -> None:
    """Remove the saved local credential and invalidate any pending login."""
    from tum_mcp.tumonline.transport import permitted_credential

    policies = PolicyStore()
    vault = Vault()
    with FileLock(str(policies.root / "connect.lock")):
        marker = policies.root / "login-generation"
        if marker.is_symlink():
            raise CampusError(Code.SCOPE_DENIED, "TUMonline login marker cannot be a symlink.")
        with vault.lease(account), vault.lock:
            record = vault.record_path(account)
            if record.exists() or record.is_symlink():
                permitted_credential(vault, account)
            private_write(marker, uuid4().hex.encode())
            record.unlink(missing_ok=True)


def save_connection(session: ResumedSession, *, attempt: str) -> AccountRef:
    """Persist service cookies and preserve any earlier permission choices."""
    account = session.account
    policies = PolicyStore()
    vault = Vault()
    with FileLock(str(policies.root / "connect.lock")):
        marker = policies.root / "login-generation"
        if marker.is_symlink():
            raise CampusError(Code.SCOPE_DENIED, "TUMonline login marker cannot be a symlink.")
        try:
            current = marker.read_text(encoding="utf-8")
        except OSError:
            raise CampusError(Code.STALE_RESULT, "TUMonline login attempt expired.") from None
        if current != attempt:
            raise CampusError(Code.STALE_RESULT, "TUMonline login attempt expired.")
        policy_path = policies.root / f"{account.id}.json"
        credential_path = vault.record_path(account)
        policy_exists = policy_path.exists() or policy_path.is_symlink()
        credential_exists = credential_path.exists() or credential_path.is_symlink()
        if policy_exists:
            policies.read(account.id)
        elif credential_exists:
            raise CampusError(Code.SCOPE_DENIED, "Saved TUMonline policy is missing.")
        else:
            policies.create(account.id)
        credential = Credential(
            account_id=account.id, authentication="browser_session", cookies=session.cookies
        )
        vault.replace_login(account, credential)
    return account


def connect_context(context: BrowserContext, attempt: str) -> AccountRef | None:
    """Detect sign-in in the shared temporary browser, then verify a resumed session."""
    from tum_mcp.moodle.auth import Cookie
    from tum_mcp.tumonline.auth import ORIGIN, PROFILE, REFRESH, STUDIES, resume_session

    cookies = tuple(
        Cookie.model_validate(item)
        for item in context.cookies([ORIGIN + REFRESH, ORIGIN + PROFILE, ORIGIN + STUDIES])
        if item["domain"].lstrip(".") == "campus.tum.de" and item["secure"]
    )
    if not cookies:
        return None
    try:
        initial, _ = resume_session(cookies)
        verified, _ = resume_session(initial.cookies, expected=initial.account)
    except CampusError as error:
        if error.code == Code.AUTH_REQUIRED:
            return None
        raise
    return save_connection(verified, attempt=attempt)

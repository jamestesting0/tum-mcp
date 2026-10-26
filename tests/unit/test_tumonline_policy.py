from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tum_mcp.errors import CampusError
from tum_mcp.tumonline.policy import PolicyStore, Scope

ACCOUNT = "a" * 64
OTHER = "b" * 64


def store(tmp_path: Path) -> PolicyStore:
    return PolicyStore(tmp_path)


def test_new_account_only_enables_studies_and_preserves_existing_policy(tmp_path: Path) -> None:
    policies = store(tmp_path)
    first = policies.create(ACCOUNT)
    assert first.allowed == frozenset({Scope.STUDIES_COURSES})
    changed = policies.set_scope(ACCOUNT, Scope.ACADEMIC_PROGRESS, True)
    assert changed.revision == first.revision + 1
    with pytest.raises(CampusError):
        policies.create(ACCOUNT)
    assert policies.read(ACCOUNT) == changed
    assert policies.create(OTHER).allowed == frozenset({Scope.STUDIES_COURSES})


def test_missing_invalid_and_corrupt_records_fail_closed(tmp_path: Path) -> None:
    policies = store(tmp_path)
    with pytest.raises(CampusError):
        policies.read(ACCOUNT)
    with pytest.raises(CampusError):
        policies.create("../invalid")
    policies.create(ACCOUNT)
    (tmp_path / f"{ACCOUNT}.json").write_text('{"schema_version": 99}')
    with pytest.raises(CampusError):
        policies.read(ACCOUNT)
    with pytest.raises(CampusError):
        policies.create(ACCOUNT)
    (tmp_path / f"{ACCOUNT}.json").write_text(
        f'{"{"}"schema_version":1,"account_id":"{ACCOUNT}","revision":0{"}"}'
    )
    with pytest.raises(CampusError):
        policies.read(ACCOUNT)


def test_scope_updates_are_atomic_and_do_not_lose_concurrent_changes(tmp_path: Path) -> None:
    policies = store(tmp_path)
    policies.create(ACCOUNT)
    scopes = (Scope.ACADEMIC_PROGRESS, Scope.EXAMS, Scope.ADMISSION)
    with ThreadPoolExecutor(max_workers=len(scopes)) as pool:
        list(pool.map(lambda scope: store(tmp_path).set_scope(ACCOUNT, scope, True), scopes))
    result = policies.read(ACCOUNT)
    assert result.allowed == frozenset({Scope.STUDIES_COURSES, *scopes})
    assert result.revision == len(scopes)
    revoked = policies.set_scope(ACCOUNT, Scope.STUDIES_COURSES, False)
    assert revoked.allows(Scope.STUDIES_COURSES) is False


def test_symlinked_record_is_never_read_or_replaced(tmp_path: Path) -> None:
    policies = store(tmp_path)
    target = tmp_path / "outside"
    target.write_text("unchanged")
    (tmp_path / f"{ACCOUNT}.json").symlink_to(target)
    with pytest.raises(CampusError):
        policies.create(ACCOUNT)
    with pytest.raises(CampusError):
        policies.read(ACCOUNT)
    assert target.read_text() == "unchanged"


def _grant_in_process(root: str, scope: str) -> None:
    PolicyStore(Path(root)).set_scope(ACCOUNT, Scope(scope), True)


def test_scope_updates_across_processes_preserve_every_change(tmp_path: Path) -> None:
    import multiprocessing

    policies = store(tmp_path)
    policies.create(ACCOUNT)
    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_grant_in_process, args=(str(tmp_path), scope.value))
        for scope in (Scope.ACADEMIC_PROGRESS, Scope.EXAMS, Scope.ADMISSION)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0
    result = policies.read(ACCOUNT)
    assert result.revision == 3
    assert result.allowed == frozenset(
        {Scope.STUDIES_COURSES, Scope.ACADEMIC_PROGRESS, Scope.EXAMS, Scope.ADMISSION}
    )


def test_unknown_scope_is_rejected_without_falling_back_to_default(tmp_path: Path) -> None:
    policies = store(tmp_path)
    policies.create(ACCOUNT)
    (tmp_path / f"{ACCOUNT}.json").write_text(
        f'{{"schema_version":1,"account_id":"{ACCOUNT}","revision":0,"allowed":["unrecognized"]}}'
    )
    with pytest.raises(CampusError):
        policies.read(ACCOUNT)


def test_policy_file_has_private_permissions(tmp_path: Path) -> None:
    import os
    import stat

    if os.name != "posix":
        pytest.skip("POSIX mode bits do not express Windows ACLs")
    policies = store(tmp_path)
    policies.create(ACCOUNT)
    assert stat.S_IMODE((tmp_path / f"{ACCOUNT}.json").stat().st_mode) == 0o600


def test_scope_replacement_rejects_unrecognized_values(tmp_path: Path) -> None:
    policies = store(tmp_path)
    original = policies.create(ACCOUNT)
    with pytest.raises(CampusError):
        policies.save_scopes(original, frozenset({"unknown"}))
    assert policies.read(ACCOUNT) == original

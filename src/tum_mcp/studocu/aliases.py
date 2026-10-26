"""Prepare safe changes to one-hop aliases of retained original PDFs."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from tum_mcp.errors import CampusError, Code
from tum_mcp.study_models import ResourceState, material_path
from tum_mcp.study_store import Write, confined, digest, private_name, private_path, read_bytes


@dataclass(frozen=True, slots=True)
class Promotion:
    writes: tuple[Write, ...] = ()
    cleanup: tuple[Write, ...] = ()


def _signature(item: ResourceState) -> tuple[str, str, str, str, int, str, int] | None:
    source = item.resource.studocu
    if (
        source is None
        or source.year is None
        or source.page_count is None
        or item.sha256 is None
        or item.status != "current"
        or item.alias_of is not None
        or item.path is None
    ):
        return None
    return (
        item.resource.binding,
        source.course_id,
        source.storage_group,
        source.document_type,
        source.year,
        item.sha256,
        source.page_count,
    )


def promote_alias(
    root: Path,
    resources: dict[str, ResourceState],
    key: str,
    *,
    retain: frozenset[str] = frozenset(),
) -> Promotion:
    """Keep aliases readable before their canonical original is moved or replaced."""
    aliases = sorted(
        (
            item
            for item in resources.values()
            if item.alias_of == key and item.resource.key not in retain
        ),
        key=lambda item: item.resource.key,
    )
    if not aliases:
        return Promotion()
    canonical = resources[key]
    if canonical.path is None:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The alias original needs review.")
    path = confined(root, canonical.path)
    if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The alias original was edited or removed.")
    with path.open("rb") as stream:
        body = stream.read(50 * 1024 * 1024 + 1)
    if len(body) > 50 * 1024 * 1024 or digest(body) != canonical.sha256:
        raise CampusError(Code.WORKSPACE_CONFLICT, "The alias original was edited or removed.")
    promoted = aliases[0]
    destination = material_path(promoted.resource, ".pdf")
    receipt_name = private_name(root, f"studocu/promotions/{key}.json")
    receipt = json.dumps(
        {
            "canonical": key,
            "promoted": promoted.resource.key,
            "sha256": canonical.sha256,
            "destination": destination,
            "original": canonical.path,
        },
        sort_keys=True,
    ).encode()
    receipt_before = read_bytes(confined(root, receipt_name))
    destination_before = read_bytes(confined(root, destination))
    if receipt_before not in (None, receipt) or (
        destination_before is not None and (receipt_before != receipt or destination_before != body)
    ):
        raise CampusError(Code.WORKSPACE_CONFLICT, "The alias destination is occupied.")
    resources[promoted.resource.key] = promoted.model_copy(
        update={"path": destination, "alias_of": None}
    )
    for alias in aliases[1:]:
        resources[alias.resource.key] = alias.model_copy(update={"alias_of": promoted.resource.key})
    return Promotion(
        writes=(
            Write(receipt_name, receipt_before, receipt),
            Write(destination, destination_before, body),
        ),
        cleanup=(Write(receipt_name, receipt, None),),
    )


def cleanup_completed_promotions(
    root: Path, resources: dict[str, ResourceState]
) -> tuple[Write, ...]:
    """Finish cleanup after a process stopped after committing promoted state."""
    directory = private_path(root, "studocu/promotions")
    if not directory.exists():
        return ()
    writes: list[Write] = []
    for path in sorted(directory.glob("studocu-*.json")):
        if not re.fullmatch(r"studocu-[1-9][0-9]{0,19}\.json", path.name):
            continue
        relative = private_name(root, f"studocu/promotions/{path.name}")
        safe = confined(root, relative)
        if not safe.is_file() or safe.stat().st_size > 4096:
            raise CampusError(Code.WORKSPACE_CONFLICT, "Promotion recovery needs review.")
        data = safe.read_bytes()
        try:
            receipt = json.loads(data)
            canonical = receipt["canonical"]
            promoted = resources[receipt["promoted"]]
            source = promoted.resource.studocu
            original = receipt["original"]
            if (
                canonical != path.stem
                or source is None
                or original != f"materials/studocu/{source.storage_group}/material-{canonical}.pdf"
                or promoted.sha256 != receipt["sha256"]
                or promoted.path != receipt["destination"]
                or promoted.alias_of is not None
            ):
                continue  # The promotion may not yet have committed its state.
            target = confined(root, promoted.path)
            if not target.is_file() or target.stat().st_size > 50 * 1024 * 1024:
                raise ValueError
            target_body = target.read_bytes()
            if digest(target_body) != promoted.sha256:
                raise ValueError
            writes.append(Write(promoted.path, target_body, target_body))
            if all(item.path != original for item in resources.values()):
                old = confined(root, original)
                if old.exists():
                    if not old.is_file() or old.stat().st_size > 50 * 1024 * 1024:
                        raise ValueError
                    body = old.read_bytes()
                    if body != target_body:
                        raise ValueError
                    writes.append(Write(original, body, None))
            writes.append(Write(relative, data, None))
        except (KeyError, TypeError, ValueError, OSError):
            raise CampusError(Code.WORKSPACE_CONFLICT, "Promotion recovery needs review.") from None
    return tuple(writes)


def consolidate_alias(
    root: Path, resources: dict[str, ResourceState], key: str, target_key: str
) -> tuple[Write, ...]:
    """Convert an existing unchanged duplicate to an alias, preserving edited files."""
    item, target = resources.get(key), resources.get(target_key)
    if item is None or target is None or item.path is None:
        return ()
    if target.alias_of is not None:
        target = resources.get(target.alias_of)
    if (
        target is None
        or target.resource.key == key
        or target.path is None
        or item.status != "current"
        or target.status != "current"
    ):
        return ()
    source, other = item.resource.studocu, target.resource.studocu
    if (
        source is None
        or other is None
        or source.year is None
        or item.sha256 != target.sha256
        or source.page_count != other.page_count
        or item.resource.binding != target.resource.binding
        or (source.course_id, source.storage_group, source.document_type, source.year)
        != (other.course_id, other.storage_group, other.document_type, other.year)
    ):
        return ()
    paths = [confined(root, item.path), confined(root, target.path)]
    if any(not path.is_file() or path.stat().st_size > 50 * 1024 * 1024 for path in paths):
        return ()
    bodies = []
    for path in paths:
        with path.open("rb") as stream:
            bodies.append(stream.read(50 * 1024 * 1024 + 1))
    if (
        len(bodies[0]) > 50 * 1024 * 1024
        or bodies[0] != bodies[1]
        or digest(bodies[0]) != item.sha256
    ):
        return ()
    resources[key] = item.model_copy(update={"path": None, "alias_of": target.resource.key})
    for dependent in tuple(resources.values()):
        if dependent.alias_of == key:
            resources[dependent.resource.key] = dependent.model_copy(
                update={"alias_of": target.resource.key}
            )
    return (Write(target.path, bodies[1], bodies[1]), Write(item.path, bodies[0], None))


def consolidate_reclassified(
    root: Path, resources: dict[str, ResourceState], changed: set[str], moving: set[str]
) -> tuple[Write, ...]:
    """Reconsider changed metadata against compatible, already stored originals."""
    groups: dict[tuple[str, str, str, str, int, str, int], list[str]] = {}
    for key, item in sorted(resources.items()):
        signature = _signature(item)
        if signature is None or item.path in moving:
            continue
        groups.setdefault(signature, []).append(key)
    writes: list[Write] = []
    for keys in groups.values():
        if len(keys) < 2:
            continue
        keys.sort(key=lambda key: (key in changed, key))
        for key in keys[1:]:
            if key not in changed or resources[key].alias_of is not None:
                continue
            for target in keys:
                if target == key or resources[target].alias_of is not None:
                    continue
                removal = consolidate_alias(root, resources, key, target)
                if removal:
                    writes.extend(removal)
                    break
    return tuple(writes)


def consolidate_moving(
    root: Path,
    resources: dict[str, ResourceState],
    creates: list[Write],
    removes: list[Write],
    changed: set[str],
) -> None:
    """Alias moved originals to byte-identical retained or concurrently moved files."""
    moving = {write.relative for write in (*creates, *removes) if write.before != write.after}
    pending_files = {write.relative: write for write in creates if write.before is None}
    targets: dict[tuple[str, str, str, str, int, str, int], list[ResourceState]] = {}
    for target in resources.values():
        signature = _signature(target)
        if signature is not None and (target.path not in moving or target.path in pending_files):
            targets.setdefault(signature, []).append(target)
    for items in targets.values():
        items.sort(key=lambda item: (item.path in moving, item.resource.key))
    for key in sorted(changed):
        item = resources[key]
        signature = _signature(item)
        if signature is None:
            continue
        pending = next(
            (write for write in creates if write.relative == item.path and write.before is None),
            None,
        )
        if pending is None or pending.after is None:
            continue
        for target in targets.get(signature, []):
            target_key = target.resource.key
            if target_key == key or resources[target_key].alias_of is not None:
                continue
            planned = pending_files.get(target.path)
            if planned is not None:
                if target_key in changed and target_key > key:
                    continue
                body = planned.after
            else:
                path = confined(root, target.path)
                if not path.is_file() or path.stat().st_size > 50 * 1024 * 1024:
                    continue
                with path.open("rb") as stream:
                    body = stream.read(50 * 1024 * 1024 + 1)
            if body is None:
                continue
            if body != pending.after or digest(body) != target.sha256:
                continue
            resources[key] = item.model_copy(update={"path": None, "alias_of": target.resource.key})
            for dependent in tuple(resources.values()):
                if dependent.alias_of == key:
                    resources[dependent.resource.key] = dependent.model_copy(
                        update={"alias_of": target.resource.key}
                    )
            creates.remove(pending)
            pending_files.pop(item.path)
            removes.append(Write(target.path, body, body))
            break


def cleanup_staging(
    root: Path, name: str, source: ResourceState, original: str
) -> tuple[Write, ...]:
    """Remove a completed legacy staging copy only when its receipt and bytes agree."""
    relative = private_name(root, f"studocu/incoming/{name}")
    path = confined(root, relative)
    receipt = confined(root, relative + ".json")
    original_path = confined(root, original)
    if (
        not path.is_file()
        or path.stat().st_size > 50 * 1024 * 1024
        or not receipt.is_file()
        or receipt.stat().st_size > 4096
        or not original_path.is_file()
        or original_path.stat().st_size > 50 * 1024 * 1024
    ):
        return ()
    try:
        info = json.loads(receipt.read_bytes())
        with path.open("rb") as stream:
            body = stream.read(50 * 1024 * 1024 + 1)
        with original_path.open("rb") as stream:
            retained = stream.read(50 * 1024 * 1024 + 1)
        if (
            info["document_id"] != source.resource.studocu.document_id
            or info["sha256"] != source.sha256
            or info["identity_basis"] != "user_selected_file"
            or info.get("validation", "validated") != "validated"
            or len(body) > 50 * 1024 * 1024
            or digest(body) != source.sha256
            or body != retained
        ):
            return ()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return ()
    return (Write(original, retained, retained), Write(relative, body, None))

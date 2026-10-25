"""Minimal catch-up checkpoints; no conversation text is persisted."""

import time

from filelock import FileLock

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.parsing import decode
from tum_mcp.settings import Frozen, data_dir
from tum_mcp.zulip import Zulip
from tum_mcp.zulip_models import Query


class Checkpoint(Frozen):
    account_id: str
    channel_id: int
    message_id: int
    message_timestamp: int
    summarized_at: float


def get_checkpoint(provider: Zulip, channel_id: int) -> Checkpoint | None:
    provider.require_channel(channel_id)
    path = data_dir() / "checkpoints" / f"{provider.api.account.id}-{channel_id}.json"
    if not path.exists():
        return None
    result = decode(Checkpoint, path.read_bytes())
    if result.account_id != provider.api.account.id or result.channel_id != channel_id:
        raise CampusError(Code.SCOPE_DENIED, "Checkpoint belongs to another account/channel.")
    return result


def save_checkpoint(provider: Zulip, channel_id: int, message_id: int) -> Checkpoint:
    page = provider.messages(Query(channel_id=channel_id), message_id=message_id)
    if not page.messages:
        raise CampusError(
            Code.CAPABILITY_UNSUPPORTED, "Checkpoint message is no longer accessible."
        )
    directory = data_dir() / "checkpoints"
    directory.mkdir(mode=0o700, exist_ok=True)
    path = directory / f"{provider.api.account.id}-{channel_id}.json"
    with FileLock(str(path.with_suffix(".lock"))):
        if path.exists():
            previous = decode(Checkpoint, path.read_bytes())
            if previous.message_id > message_id:
                raise CampusError(Code.SCOPE_DENIED, "Checkpoint cannot move backwards.")
        record = Checkpoint(
            account_id=provider.api.account.id,
            channel_id=channel_id,
            message_id=message_id,
            message_timestamp=page.messages[0].timestamp,
            summarized_at=time.time(),
        )
        private_write(path, record.model_dump_json().encode())
        return record

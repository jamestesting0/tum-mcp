import errno
import os
from collections.abc import Callable, Generator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from hashlib import sha256
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Annotated, Final

from filelock import FileLock, Timeout
from pydantic import Field, TypeAdapter, ValidationError

from tum_mcp.errors import CampusError, Code
from tum_mcp.moodle.config import private_write
from tum_mcp.settings import Frozen, config_dir

DEFAULT_PORT: Final = 8765
OCCUPIED: Final = frozenset({errno.EADDRINUSE, 10048})
WSAEACCES: Final = 10013
type Port = Annotated[int, Field(strict=True, ge=1, le=65535)]
type BindPreview = Callable[[int], ThreadingHTTPServer]


class PreviewPorts(Frozen):
    preferred: Port
    active: Port


_PORTS: Final = TypeAdapter(dict[str, PreviewPorts])


@dataclass(frozen=True, slots=True)
class PreviewSession:
    ports: PreviewPorts
    server: ThreadingHTTPServer | None = None


def _available_server(bind: BindPreview, reserved: set[int]) -> ThreadingHTTPServer:
    with ExitStack() as excluded:
        while (server := bind(0)).server_port in reserved:
            _ = excluded.enter_context(server)
        return server


@contextmanager
def automatic_preview(root: Path, bind: BindPreview) -> Generator[PreviewSession]:
    """Keep the project lock for the lifetime of its bound preview socket."""
    folder = config_dir()
    registry = folder / "study-preview-ports.json"
    project_id = sha256(os.fsencode(os.path.normcase(root))).hexdigest()
    lease = FileLock(str(folder / f"study-preview-{project_id}.lock"), timeout=0)
    registry_lock = FileLock(str(registry.with_suffix(".lock")))
    with ExitStack() as lifetime:
        with registry_lock:
            try:
                assignments = _PORTS.validate_json(registry.read_bytes())
            except FileNotFoundError:
                assignments = {}
            except ValidationError:
                raise CampusError(
                    Code.ACTION_REQUIRED,
                    "Study preview port settings are invalid. Inspect them or use --port PORT.",
                ) from None
            previous = assignments.get(project_id)
            try:
                _ = lifetime.enter_context(lease)
            except Timeout:
                if previous is None:
                    raise CampusError(
                        Code.ACTION_REQUIRED,
                        "A preview for this project is running. Find its URL in its terminal.",
                    ) from None
                session = PreviewSession(previous)
            else:
                reserved = {ports.preferred for ports in assignments.values()}
                candidates = (
                    (previous.preferred,)
                    if previous is not None
                    else (
                        port
                        for port in range(DEFAULT_PORT, DEFAULT_PORT + 32)
                        if port not in reserved
                    )
                )
                for port in candidates:
                    try:
                        server = bind(port)
                    except OSError as error:
                        if error.errno not in OCCUPIED and error.errno != WSAEACCES:
                            raise
                    else:
                        break
                else:
                    server = _available_server(bind, reserved)
                _ = lifetime.enter_context(server)
                ports = PreviewPorts(
                    preferred=previous.preferred if previous is not None else server.server_port,
                    active=server.server_port,
                )
                if ports != previous:
                    assignments[project_id] = ports
                    private_write(registry, _PORTS.dump_json(assignments))
                session = PreviewSession(ports, server)
        try:
            yield session
        finally:
            if session.server is not None:
                with registry_lock:
                    lifetime.close()

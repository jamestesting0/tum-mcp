"""The preview's Ask agent endpoints: provider connection, chats and streamed turns.

Same-origin like the comment API, plus a per-start token in a custom header, because these
endpoints start an agent that can edit the course. Turns stream as newline-delimited JSON.
"""

import json
import secrets
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Literal
from uuid import UUID

from filelock import FileLock, Timeout
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from tum_mcp.course.app import ask_edits, ask_runtime, ask_threads
from tum_mcp.course.app.ask_context import ANCHOR, View, anchor_file, location, packet
from tum_mcp.course.app.comment_api import reply, same_origin
from tum_mcp.course.project.store import private_path
from tum_mcp.errors import CampusError, Code

PREFIX = "/_study/agent/"
HEADER = "X-Ask-Token"
IDLE = 600  # seconds a chat's live Claude process may wait for the next message
CHECKED = 60  # seconds the sign-in checks are reused
LIVE = 3  # live Claude processes kept at most, the most recently used


class Send(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat: UUID | None = None
    text: str = Field(min_length=1, max_length=8000)
    anchor: dict | None = None
    view: View = View()
    place: str = Field(default="", max_length=200)
    scope: Literal["selection", "section"] = "selection"
    quote: str = Field(default="", max_length=2000)
    section: str = Field(default="", max_length=200)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: ask_runtime.Provider
    model: str = Field(max_length=100)
    effort: str = Field(max_length=20)


class Account(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ask_runtime.Profile


class Connect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: ask_runtime.Provider
    key: str | None = Field(default=None, max_length=300)


class Service:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.token = secrets.token_urlsafe(32)
        self.codex: dict[str, ask_runtime.Codex] = {}
        self.turns: dict[UUID, object] = {}
        self.claude: dict[UUID, ask_runtime.ClaudeSession] = {}
        self.active: str | None = None
        self.checked: tuple[float, dict[str, dict]] | None = None
        self.warmed = False
        self.lock = threading.Lock()
        threading.Thread(target=self._reap, daemon=True).start()

    def _reap(self) -> None:
        while True:
            time.sleep(60)
            self._trim()

    def _trim(self, keep: UUID | None = None) -> None:
        """Closes live Claude processes that went idle, and the oldest beyond the limit."""
        with self.lock:
            ordered = sorted(self.claude.items(), key=lambda item: item[1].used, reverse=True)
            now = time.monotonic()
            for index, (chat, live) in enumerate(ordered):
                busy = chat in self.turns or chat == keep
                if not busy and (index >= LIVE or now - live.used > IDLE or not live.alive()):
                    del self.claude[chat]
                    threading.Thread(target=live.close, daemon=True).start()

    def close_claude(self) -> None:
        """Closes the idle live Claude processes; a running turn finishes on its own."""
        with self.lock:
            idle = [chat for chat in self.claude if chat not in self.turns]
            sessions = [self.claude.pop(chat) for chat in idle]
        for live in sessions:
            live.close()

    def codex_server(self, profile: str = "codex-subscription") -> ask_runtime.Codex:
        name = ask_runtime.CODEX_HOMES.get(profile, "codex")
        with self.lock:
            server = self.codex.get(name)
            if server is None or not server.alive():
                server = self.codex[name] = ask_runtime.Codex(name)
            return server

    def _codex_status(self) -> dict:
        if not ask_runtime.shutil.which("codex"):
            return {"installed": False, "connected": False}
        try:
            return self.codex_server().status()
        except CampusError:
            return {"installed": True, "connected": False}

    def _providers(self, fresh: bool) -> dict[str, dict]:
        """Each CLI's sign-in, asked in parallel and reused for a minute; account changes made
        here clear it, and the sign-in wait asks fresh."""
        checked = self.checked
        if not fresh and checked and time.monotonic() - checked[0] < CHECKED:
            return checked[1]
        with ThreadPoolExecutor(3) as pool:
            claude = pool.submit(ask_runtime.claude_status)
            codex = pool.submit(self._codex_status)
            cursor = pool.submit(ask_runtime.cursor_status)
            providers = {
                "claude": claude.result(),
                "codex": codex.result(),
                "cursor": cursor.result(),
            }
        self.checked = (time.monotonic(), providers)
        return providers

    def status(self, *, fresh: bool = False) -> dict:
        providers = self._providers(fresh)
        claude, codex, cursor = providers["claude"], providers["codex"], providers["cursor"]
        # Each signed-in account is a profile; the student switches between them in the app.
        profiles = [
            {"id": "claude-subscription", "provider": "claude", "method": claude.get("method")}
            if claude["connected"]
            else None,
            {"id": "claude-key", "provider": "claude", "method": "API key"}
            if claude["installed"] and ask_runtime.has_key()
            else None,
            {"id": "codex-subscription", "provider": "codex", "method": codex.get("method")}
            if codex["connected"]
            else None,
            {"id": "codex-key", "provider": "codex", "method": "API key"}
            if codex["installed"] and ask_runtime.has_codex_key()
            else None,
            {"id": "cursor-subscription", "provider": "cursor", "method": cursor.get("method")}
            if cursor["connected"]
            else None,
            {"id": "cursor-key", "provider": "cursor", "method": "API key"}
            if cursor["installed"] and ask_runtime.has_cursor_key()
            else None,
        ]
        profiles = [profile for profile in profiles if profile]
        active = next(
            (item for item in profiles if item["id"] == ask_runtime.chosen()),
            profiles[0] if profiles else None,
        )
        provider = active["provider"] if active else None
        if not self.warmed:
            # The other accounts' model menus load in the background, so a switch shows at once.
            self.warmed = True
            others = [item for item in profiles if item is not active]
            threading.Thread(target=self._warm, args=(others,), daemon=True).start()
        return {
            "token": self.token,
            "provider": provider,
            "profile": active["id"] if active else None,
            "profiles": profiles,
            "providers": providers,
            "options": self.options(provider, active["id"]) if active else None,
        }

    def _warm(self, profiles: list[dict]) -> None:
        for item in profiles:
            self.models(item["provider"], item["id"])

    def models(self, provider: ask_runtime.Provider, profile: str | None = None) -> list[dict]:
        if provider == "claude":
            return ask_runtime.claude_models()
        if provider == "cursor":
            return ask_runtime.cursor_models(key=profile == "cursor-key")
        try:
            return self.codex_server(profile or "codex-subscription").models()
        except CampusError:
            return []

    def options(self, provider: ask_runtime.Provider, profile: str | None = None) -> dict | None:
        models = self.models(provider, profile)
        return ask_runtime.options(provider, models) if models else None

    def settings(self, request: Settings) -> dict | None:
        chosen = ask_runtime.chosen() or ""
        profile = chosen if chosen.startswith(request.provider) else None
        model = next(
            (
                item
                for item in self.models(request.provider, profile)
                if item["id"] == request.model
            ),
            None,
        )
        # A model without effort levels (Cursor's Auto) takes no effort.
        if model is None or request.effort not in (model["efforts"] or [""]):
            raise ValueError("unknown model or effort")
        ask_runtime.prefer(request.provider, request.model, request.effort, model.get("family", ""))
        return self.options(request.provider, profile)

    def connect(self, request: Connect) -> dict:
        self.checked = None
        url = None
        if request.provider == "claude":
            if request.key:
                ask_runtime.save_key(request.key)
            else:
                ask_runtime.claude_login()
        elif request.provider == "cursor":
            if request.key:
                ask_runtime.save_cursor_key(request.key)
            else:
                ask_runtime.cursor_login()
        else:
            profile = "codex-key" if request.key else "codex-subscription"
            url = self.codex_server(profile).sign_in(request.key)
            if request.key:
                ask_runtime.mark_codex_key(True)
        if url:
            webbrowser.open(url)
        # A saved key is ready at once. A browser sign-in becomes active only when the app sees
        # it finish, so an abandoned sign-in never changes the account in use.
        if request.key:
            ask_runtime.choose(f"{request.provider}-key")
        return {"pending": not request.key, "url": url}

    def switch(self, profile: ask_runtime.Profile) -> dict:
        """Makes another signed-in account active and returns the new status.

        A switch changes no sign-in, so the cached checks stay; idle Claude processes close in
        the background, and a running one restarts on its next message.
        """
        threading.Thread(target=self.close_claude, daemon=True).start()
        ask_runtime.choose(profile)
        return self.status()

    def disconnect(self, profile: ask_runtime.Profile) -> None:
        self.checked = None
        self.close_claude()
        if profile == "claude-key":
            ask_runtime.forget_key()
        elif profile == "claude-subscription":
            ask_runtime.claude_logout()
        elif profile == "cursor-key":
            ask_runtime.forget_cursor_key()
        elif profile == "cursor-subscription":
            ask_runtime.cursor_logout()
        else:
            self.codex_server(profile).sign_out()
            if profile == "codex-key":
                ask_runtime.mark_codex_key(False)
        if ask_runtime.chosen() == profile:
            ask_runtime.choose(None)

    def _turn(self, provider: ask_runtime.Provider, chat: ask_threads.Chat, prompt: str):
        chosen = self.options(provider, self.active) or {}
        model, effort = chosen.get("model", ""), chosen.get("effort", "")
        if provider == "cursor":
            # A Cursor model runs as the variant for the chosen effort (claude-opus-5-5-high).
            item = next((m for m in chosen.get("models", []) if m["id"] == model), {})
            model = item.get("variants", {}).get(effort, model)
            return ask_runtime.CursorTurn(
                self.root, chat.session or None, prompt, model, key=self.active == "cursor-key"
            )
        if provider == "codex":
            return ask_runtime.CodexTurn(
                self.codex_server(self.active or "codex-subscription"),
                self.root,
                chat.session or None,
                prompt,
                model,
                effort,
            )
        key = self.active == "claude-key"
        with self.lock:
            live = self.claude.get(chat.id)
            if live and (not live.alive() or live.choice != (model, effort, key)):
                threading.Thread(target=live.close, daemon=True).start()
                live = None
            if live is None:
                live = ask_runtime.ClaudeSession(
                    self.root, chat.session or None, model, effort, key=key
                )
                self.claude[chat.id] = live
        self._trim(keep=chat.id)
        return ask_runtime.ClaudeTurn(live, prompt)

    def _moved(self, chat: ask_threads.Chat, provider: str) -> bool:
        """Whether the chat's agent session cannot follow it to the active account.

        Claude's subscription and key share one home, so a session resumes under either; each
        Codex and Cursor account keeps its sessions apart.
        """
        if chat.provider != provider:
            return True
        return provider != "claude" and (chat.profile or f"{provider}-subscription") != self.active

    def send(self, request: Send):
        state = self.status()
        provider, self.active = state["provider"], state["profile"]
        if provider is None:
            raise CampusError(Code.AUTH_REQUIRED, "Connect an account first.")
        anchor = ANCHOR.validate_python(request.anchor) if request.anchor else None
        if request.chat:
            chat = ask_threads.read(self.root, request.chat)
            first = not chat.messages or self._moved(chat, provider)
        else:
            chat = ask_threads.create(
                self.root,
                provider,
                title=request.text,
                place=request.place,
                route=request.view.route,
                anchor=request.anchor,
            )
            first = True
        if self._moved(chat, provider):
            chat = chat.model_copy(update={"provider": provider, "session": ""})
            with self.lock:
                stale = self.claude.pop(chat.id, None)
            if stale is not None:
                threading.Thread(target=stale.close, daemon=True).start()
        chat = chat.model_copy(update={"profile": self.active or ""})
        # A follow-up repeats no context it already sent: a new selection or section in view
        # gets a brief packet, and the same section again gets none.
        section = request.scope == "section"
        where = location(anchor) if anchor else ""
        if first:
            context = packet(
                self.root, anchor, request.view, [], section=section, quote=request.quote
            )
        elif anchor and not (section and where == chat.context):
            context = packet(
                self.root,
                anchor,
                request.view,
                [],
                section=section,
                quote=request.quote,
                brief=True,
            )
        else:
            context = ""
        if anchor:
            chat = chat.model_copy(update={"context": where})
        prompt = f"{context}\n\n{request.text}" if context else request.text
        if first and chat.messages:
            prompt = f"{_history(chat)}\n\n{prompt}"
        now = datetime.now(UTC)
        chat = ask_threads.append(
            self.root,
            chat,
            ask_threads.Message(
                role="student",
                text=request.text,
                at=now,
                quote=(request.quote or anchor.quote) if anchor and not section else "",
                section=request.section if anchor else "",
            ),
        )
        yield {"type": "chat", "id": str(chat.id)}
        lock = FileLock(str(private_path(self.root, "agent/edit.lock")), timeout=0)
        try:
            lock.acquire()
        except Timeout:
            yield {"type": "error", "text": "Another Ask agent turn is running in this course."}
            return
        # The anchored item's lint problems before the turn, computed while the agent works,
        # so the edit gate blocks only the problems the edit introduced.
        anchored = anchor or (ANCHOR.validate_python(chat.anchor) if chat.anchor else None)
        names = [anchor_file(anchored)] if anchored else []
        try:
            yield from self._run(chat, provider, prompt, ask_edits.Baseline(self.root, names))
        finally:
            lock.release()

    def _run(
        self, chat: ask_threads.Chat, provider: str, prompt: str, baseline: ask_edits.Baseline
    ):
        before = ask_edits.snapshot(self.root)
        log = WorkLog()
        text, error = "", None
        changes: dict[str, tuple[bytes | None, bytes | None]] = {}
        reverted: list[str] = []
        for attempt in range(2):
            turn = self._turn(provider, chat, prompt)
            self.turns[chat.id] = turn
            chat = ask_threads.save(self.root, chat.model_copy(update={"session": turn.session}))
            for event in ask_runtime.stream(turn.events()):
                if event["type"] == "final":
                    text = event["text"]
                elif event["type"] == "error":
                    error = event["text"]
                else:
                    yield log.take(event)
            self.turns.pop(chat.id, None)
            # Cursor names a new session only once it starts, so it is saved again afterwards.
            if turn.session and turn.session != chat.session:
                chat = ask_threads.save(
                    self.root, chat.model_copy(update={"session": turn.session})
                )
            reverted = ask_edits.revert_protected(self.root, before)
            changes = ask_edits.changed(self.root, before)
            if error or not changes:
                break
            problem, checks = ask_edits.rebuild(self.root), False
            if problem is None:
                yield log.take({"type": "status", "text": "Checking the edit", "after": True})
                problem, checks = baseline.new_problems(changes), True
            if problem is None:
                break
            if attempt == 1:
                ask_edits.restore(self.root, changes)
                ask_edits.rebuild(self.root)
                failed = "pass the course checks" if checks else "build"
                changes, error = {}, f"The edit did not {failed}, so it was undone: {problem[:300]}"
                break
            yield log.take({"type": "status", "text": "Fixing the edit"})
            prompt = (
                f"The course checks found problems your edit introduced. Fix them:\n{problem}"
                if checks
                else f"The app build failed after your edit. Fix it:\n{problem}"
            )
        change = None
        if changes and not error:
            edit = ask_edits.record(self.root, changes)
            change = ask_threads.Change(
                id=edit,
                sections=tuple(ask_edits.sections(changes)),
                summary=next(
                    (line for line in text.splitlines() if line.startswith("Updated")), ""
                )[:400],
            )
        if reverted:
            yield log.take(
                {"type": "status", "text": "Kept protected course files unchanged", "after": True}
            )
        message = ask_threads.Message(
            role="agent",
            text=error or text or "No answer.",
            at=datetime.now(UTC),
            change=change,
            log=log.finish(text),
            worked=log.worked,
        )
        ask_threads.append(self.root, chat, message)
        yield {"type": "message", "message": json.loads(message.model_dump_json())}
        yield {"type": "done", "edited": change is not None}

    def interrupt(self, chat: UUID) -> None:
        turn = self.turns.get(chat)
        if turn is not None:
            turn.interrupt()

    def undo(self, chat: UUID, edit: str, *, redo: bool = False) -> None:
        with FileLock(str(private_path(self.root, "agent/edit.lock")), timeout=5):
            (ask_edits.redo if redo else ask_edits.undo)(self.root, edit)
        found = ask_threads.read(self.root, chat)
        messages = tuple(
            item.model_copy(update={"change": item.change.model_copy(update={"undone": not redo})})
            if item.change and item.change.id == edit
            else item
            for item in found.messages
        )
        ask_threads.save(self.root, found.model_copy(update={"messages": messages}))

    def chat(self, chat: UUID) -> dict:
        found = ask_threads.public(ask_threads.read(self.root, chat))
        for message in found["messages"]:
            if change := message.get("change"):
                if change["undone"]:
                    change["redoable"] = ask_edits.redoable(self.root, change["id"])
                else:
                    change["undoable"] = ask_edits.undoable(self.root, change["id"])
        return found


LOG_TEXT = 600  # characters kept of one log line; thinking summaries are cut here
LOG_STEPS = 40  # log lines kept with an answer, the latest


class WorkLog:
    """The agent's work during a turn, kept compact with its answer.

    Steps are tool calls and the preview's checks; notes are text the agent wrote before a tool
    call; thinking entries say how long it thought, with the summary Codex shares. The text after
    the last step is the answer itself, so it is not kept twice.
    """

    def __init__(self) -> None:
        self.steps: list[ask_threads.Step] = []
        self.note = ""
        self.thinking: tuple[float, str] | None = None
        self.started = time.monotonic()

    def take(self, event: dict) -> dict:
        kind = event["type"]
        if kind == "thinking":
            if self.thinking is None:
                self._note()
                self.thinking = (time.monotonic(), "")
            self.thinking = (self.thinking[0], self.thinking[1] + event.get("text", ""))
            return event
        self._thought()
        if kind == "note":
            self.note += event["text"]
        elif kind == "status":
            # The preview's own checks come after the answer, which stays pending until finish.
            if not event.get("after"):
                self._note()
            last = self.steps[-1] if self.steps else None
            if event["text"] != "Working" and not (last and last.text == event["text"]):
                self._add("step", event["text"])
        return event

    def finish(self, answer: str) -> tuple[ask_threads.Step, ...]:
        self._thought()
        note = " ".join(self.note.split())
        if note and not " ".join(answer.split()).startswith(note[:80]):
            self._note()
        return tuple(self.steps[-LOG_STEPS:])

    @property
    def worked(self) -> int:
        return max(1, round(time.monotonic() - self.started))

    def _add(self, kind: str, text: str, seconds: int = 0) -> None:
        text = text.strip()
        if len(text) > LOG_TEXT:
            text = text[: LOG_TEXT - 1].rstrip() + "\u2026"
        self.steps.append(ask_threads.Step(kind=kind, text=text, seconds=seconds))

    def _note(self) -> None:
        if self.note.strip():
            self._add("note", " ".join(self.note.split()))
        self.note = ""

    def _thought(self) -> None:
        if self.thinking is not None:
            start, text = self.thinking
            self.thinking = None
            self._add("thinking", text, max(1, round(time.monotonic() - start)))


HISTORY = 24000  # characters of earlier chat a new agent session receives, newest first


def _history(chat: ask_threads.Chat) -> str:
    """The chat so far, for an agent session that did not see it (another account or provider).

    Chats belong to the course, not to an account, so any account can continue one. The newest
    messages are kept whole while they fit; older ones are dropped first.
    """
    lines: list[str] = []
    room = HISTORY
    for item in reversed(chat.messages):
        about = f' (about "{item.quote[:300]}")' if item.quote else ""
        line = f"{item.role}{about}: {item.text[:4000]}"
        if len(line) > room:
            break
        lines.append(line)
        room -= len(line)
    body = "\n\n".join(reversed(lines))
    return f"<earlier-chat>\n{body}\n</earlier-chat>"


def _service(handler: BaseHTTPRequestHandler, directory: str) -> Service:
    server = handler.server
    if getattr(server, "ask", None) is None:
        server.ask = Service(Path(directory).resolve().parent)
    return server.ask


def _body(handler: BaseHTTPRequestHandler) -> bytes:
    size = int(handler.headers.get("Content-Length", "0"))
    if not 0 < size <= 65536 or handler.headers.get_content_type() != "application/json":
        raise ValueError("bad request")
    return handler.rfile.read(size)


def _stream(handler: BaseHTTPRequestHandler, events) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
    handler.end_headers()
    try:
        for event in events:
            handler.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
            handler.wfile.flush()
    except CampusError as error:
        handler.wfile.write((json.dumps({"type": "error", "text": error.message}) + "\n").encode())
    except (BrokenPipeError, ConnectionResetError):
        return


def handle(handler: BaseHTTPRequestHandler, directory: str, *, write: bool) -> None:
    if not same_origin(handler, require_origin=write):
        reply(handler, 403, {"error": "Ask agent requires the local preview origin."})
        return
    service = _service(handler, directory)
    path = handler.path.removeprefix(PREFIX).split("?")[0]
    if path != "status" and not secrets.compare_digest(
        handler.headers.get(HEADER, ""), service.token
    ):
        reply(handler, 403, {"error": "Reload the course app."})
        return
    try:
        match (write, path.split("/")):
            case (False, ["status"]):
                reply(handler, 200, service.status(fresh="fresh=1" in handler.path))
            case (False, ["chats"]):
                reply(handler, 200, {"chats": ask_threads.listing(service.root)})
            case (False, ["chats", chat]):
                reply(handler, 200, service.chat(UUID(chat)))
            case (True, ["connect"]):
                reply(handler, 200, service.connect(Connect.model_validate_json(_body(handler))))
            case (True, ["settings"]):
                reply(
                    handler,
                    200,
                    {"options": service.settings(Settings.model_validate_json(_body(handler)))},
                )
            case (True, ["disconnect"]):
                service.disconnect(Account.model_validate_json(_body(handler)).profile)
                reply(handler, 200, {"ok": True})
            case (True, ["profile"]):
                reply(
                    handler,
                    200,
                    service.switch(Account.model_validate_json(_body(handler)).profile),
                )
            case (True, ["send"]):
                _stream(handler, service.send(Send.model_validate_json(_body(handler))))
            case (True, ["chats", chat, "interrupt"]):
                service.interrupt(UUID(chat))
                reply(handler, 200, {"ok": True})
            case (True, ["chats", chat, "delete"]):
                ask_threads.delete(service.root, UUID(chat))
                reply(handler, 200, {"ok": True})
            case (True, ["chats", chat, ("undo" | "redo") as action, edit]):
                service.undo(UUID(chat), edit, redo=action == "redo")
                reply(handler, 200, {"ok": True})
            case _:
                reply(handler, 404, {"error": "Unknown Ask agent request."})
    except (ValueError, ValidationError):
        reply(handler, 400, {"error": "Invalid Ask agent request."})
    except CampusError as error:
        reply(handler, 409, {"error": error.message})

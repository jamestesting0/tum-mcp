---
name: setup
description: Set up or reconnect the personal TUM Moodle integration on this computer.
---

Install first, prompt for sign-in, then offer an optional live course check.

If native tools are available, begin with `moodle_auth_status`; a new bootstrap
is not needed for a connected or normally expired session. For a missing/broken
runtime, run the packaged `scripts/bootstrap.py` using
`uv run --no-project --python 3.13`. It checks/reuses the private runtime and
reports credential-store problems. Use `--repair` only for a broken runtime.
Consult packaged docs/setup.md only for an error or missing prerequisite.

If tools need a reload, give one full-restart instruction and this prompt:
"Sign in to TUM Moodle." Do not repeat probes/reinstalls while waiting.
Check loader errors before asking for another restart; never operate Codex's UI.

Prompt for sign-in after software installation. Check `moodle_auth_status` and
reuse a connected session. When sign-in is needed and the user proceeds, call
`moodle_login` once and let them complete login/MFA in the selected Chromium browser. Check status after
their response; do not repeatedly open browsers or collect credentials in chat.
Explain a missing Chromium browser or a locked native credential store using the setup guide.

Once connected, ask whether to check the connection by listing current-semester
courses. Call `moodle_list_courses` only after opt-in. A declined check leaves
setup complete. Do not require lecture reads, indexing, downloads, or private records.

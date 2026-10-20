---
name: setup
description: Set up or reconnect the personal TUM Moodle integration on this computer.
---

Read the packaged docs/setup.md for the current operating system.
Run the packaged `scripts/bootstrap.py` with `uv run --no-project --python 3.13`
to prepare the private runtime. Linux requires an unlocked Secret Service desktop keyring.
The script resolves its package directory itself. Do not copy authentication state or request passwords.
After bootstrap, if tools are not available, ask the user to quit the app completely
and reopen it (Cmd+Q on macOS; exit the app fully on Windows/Linux).
Check plugin loader errors before requesting another restart.
Call `moodle_auth_status`; only if sign-in is needed, call `moodle_login` and ask the
user to complete sign-in and MFA in the private Chrome window. Poll status after the user responds.
Credentials remain in the browser and encrypted local session storage.
The runtime uses the installed Google Chrome application; explain a missing-browser error.

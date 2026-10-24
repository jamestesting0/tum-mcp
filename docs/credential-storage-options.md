# Credential storage and setup experience

Checked against project code and primary upstream documentation on 24 October 2026.

## What other projects do

| Project | Protected default | File alternative and trade-off |
| --- | --- | --- |
| [Git Credential Manager](https://github.com/git-ecosystem/git-credential-manager/blob/main/docs/credstores.md) | macOS Keychain and Windows Credential Manager; configurable Linux stores | Supports Windows DPAPI-protected files. Also offers explicitly insecure plaintext files and an ephemeral cache. |
| [Docker](https://docs.docker.com/reference/cli/docker/login/#credential-stores) | Native credential helpers; Docker Desktop configures one | Without a helper it stores base64-encoded credentials in configuration. Docker describes that as less secure. |
| [GitHub CLI](https://cli.github.com/manual/gh_auth_login) | System credential store | Supports `--insecure-storage` and documents a plain-file fallback when secure storage fails. [Its implementation](https://github.com/cli/cli/blob/trunk/internal/config/config.go#L496-L512) explicitly tracks whether insecure storage was used. |
| [Electron](https://www.electronjs.org/docs/latest/api/safe-storage) | macOS Keychain; Windows DPAPI; Linux desktop secret stores | macOS can still prompt. Its documentation recommends consistent code signing to prevent repeated approval after updates. Linux fallback backends need careful inspection because protection can be weaker. |

Saving a key elsewhere is technically possible, but location alone does not
protect it. A readable key file next to encrypted sessions lets a process that
can copy both decrypt the sessions. Restrictive file permissions help against
other OS users; they do not provide a separate secret-store boundary against
code running as the same user. This is why the protected defaults above still
use operating-system services.

## Current TUM MCP implementation

| Platform | Implemented storage | Verification and expected setup |
| --- | --- | --- |
| macOS | Native Keychain item holds the encryption key; service cookies remain in encrypted files | Real saved sessions and scoped reads passed from the managed runtime after the user approved access. OS prompts remain possible for locked items, changed application identity, or temporary approval. |
| Windows | Windows Credential Locker through Python keyring | Implementation and CI configuration exist. Hands-on Windows verification is still pending; no claim of universally prompt-free operation is made. |
| Linux | Freedesktop Secret Service through Python keyring | ARM64 and x86_64 container bootstrap passed. On x86_64, an encrypted credential round trip across separate processes passed through real GNOME Secret Service in an isolated D-Bus session. Real desktop browser sign-in remains open. A usable, unlocked service and D-Bus session are required. |

The backend selection is in `tum_moodle.auth.system_keyring`; encryption and
account binding are in `tum_mcp.credentials.Vault`. There is no automatic
plaintext fallback. The data-encryption key's service name and storage location
are stable across backend-wheel updates.

Windows can also protect a file directly with per-user
[DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).
That avoids an adjacent unprotected key file. It is a reasonable optional backend
if Credential Manager proves unsuitable, but it is not implemented in this build.
It does not remove the need for a usable Windows user/logon context.

## Why this setup prompted repeatedly

The initial account connection ran under development Python. The installed
package then used managed Python to access the same existing Keychain item.
Those were different requesting executables. Python keyring documents that
access is associated with the
[Python executable](https://keyring.readthedocs.io/en/stable/#security-considerations).
Temporary **Allow** and persistent **Always Allow** are also different choices.

The fresh-install path was tested separately with a disposable native Keychain
item: managed Python created it, then a second process of that same runtime read
it successfully in about one second without another user interaction. The item
was deleted afterward. This supports using the installed runtime from the first
login; it does not guarantee every Mac policy will suppress all prompts.

A subsequent real MCP check passed through the installed Codex plugin, its Node
launcher, and managed Python: both provider identities verified, the selected
Zulip channel was readable, and an unselected channel was denied. No remote
submission or message write was performed.

## Recommended direction

1. Keep native protected storage as the default and use the installed `tum-mcp`
   command for both onboarding and normal use.
2. Add a foreground storage-access check before opening browser login, so any
   necessary OS approval happens during setup rather than a later tool call.
   This is a proposed UX improvement, not a shipped behavior change here.
3. If future macOS interpreter updates keep changing identity, use a dedicated,
   consistently signed credential helper. That needs separate packaging/signing
   work and cannot guarantee that first-time OS approval never appears.
4. Consider explicit DPAPI-file or session-only modes for their appropriate
   platforms/use cases. Plain-file storage should require an informed choice;
   session-only storage requires signing in again after the broker stops.

These recommendations change neither the existing stored credentials nor their
permissions. Keychain approval is scoped to Python's access to this item; scripts
using the same trusted executable can also request it. A restricted MCP API is
not a system-wide sandbox for an otherwise unrestricted coding agent.

## Separate desktop-app permission

The macOS prompt naming **ChatGPT** and asking to access data from other apps is
separate from a Keychain request for `tum-mcp`. Apple associates that prompt with
[files in other apps' sandbox containers](https://developer.apple.com/documentation/BundleResources/Information-Property-List/NSAppDataUsageDescription).
The campus backend's default storage and HTTP read paths do not need that broad
host permission. The specific container behind the observed prompt was not
identified; computer-use inventory is a possible trigger, not a confirmed cause.

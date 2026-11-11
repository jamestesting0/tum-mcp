# Host references

The walkthrough rebuilds each coding agent from these sources. Update this log whenever a
rebuild changes. Screenshots stay in `references/captures/`, which is not committed.

| Host | View shown | Version | Source | Captured |
| --- | --- | --- | --- | --- |
| Codex | VS Code with the Codex extension in the secondary side bar | VS Code 1.145.3, Codex extension 26.1021.22027 | Theme colours from VS Code's `dark_modern.json` and `light_modern.json`; composer placeholder and run-location labels from the extension's webview bundle; mark from the extension's resources | 2026-11-11 |
| Claude Code | Terminal CLI | Claude Code 2.1.304 | Start screen recorded from `claude` in a pseudo-terminal (model line kept without the account's plan) | 2026-11-11 |
| Cursor | Cursor editor layout with the agent panel | Cursor 3.24.18 | Theme colours from Cursor's bundled `Cursor Dark` and `Cursor Light` themes | 2026-11-11 |
| Antigravity | Antigravity IDE, Mac | Official product page | `antigravity.google/product/antigravity-ide` editor and agent imagery (light). The dark version follows the same layout with VS Code Dark Modern neutrals; it is not taken from an official image. Not installed, by request. | 2026-11-11 |

CLI screens come from `npm run capture-cli`, which runs the real `tum-mcp setup` in a
throwaway HOME. `editor-themes.json` holds the extracted theme colours.

The rebuilds are reconstructions, not pixel copies: layouts and default themes follow the
sources above, and window contents show the synthetic Graph Search course.

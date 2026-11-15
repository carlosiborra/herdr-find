# Changelog

## 0.2.2

- Naming: write Herdr for the product and `herdr` for the command, across README, docs, manifest name ("Herdr Find"), user-facing strings and tests.
- Vendored helpers: HerdR → Herdr spelling only (no spelling hits in the helper files; recorded hashes unchanged).
- README rewritten with a benefit-first opening, install and keybinding snippet, demo caption, website link, collapsed text preview and suite links.
- CONTRIBUTING: document the naming convention.
- Manifest: version 0.2.2.

## 0.2.1

- Add a demo GIF (`docs/demo.gif`) to the README.
- Add CI, release, license and HerdR plugin badges to the README.
- Add GitHub issue templates (bug report, feature request) and disable blank issues, with a link to Security Advisories.
- Add `tests/test_vendored.py`, a drift guard that checks the sha256 of the vendored helpers (`theme.py`, `terminal.py`, `search.py`, `text.py`); documented in CONTRIBUTING.
- Manifest: version 0.2.1.

## 0.2.0

- Plugin id is now `carlosiborra.find` (namespaced, so it cannot clash with other `herdr-find` plugins). Bind actions as `carlosiborra.find.<action>`.

- Honor `HERDR_BIN_PATH` for every herdr invocation (fallback `herdr`) and `HERDR_PLUGIN_ID` for the plugin pane open.
- Read the theme from `$XDG_CONFIG_HOME/herdr/config.toml` when set, else `~/.config/herdr/config.toml`.
- Cap scrollback reads at 5000 lines per pane (was one million).
- Standalone repository: install via `herdr plugin install`, removed monorepo references, added CI, LICENSE, SECURITY and CONTRIBUTING.
- Document the raw-socket exact focus, privacy behavior and optional dependencies (fd, rg, lazygit, editor).
- Manifest: version 0.2.0, `min_herdr_version` 0.9.5.
- Tests: no hardcoded temp directory; added tests for binary path, plugin id and config path.

## 0.1.0

- Initial release: fuzzy terminal finder with exact focus, scrollback search and file/folder/ripgrep/lazygit pickers.

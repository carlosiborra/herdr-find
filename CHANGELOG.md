# Changelog

## 0.2.0

- Honor `HERDR_BIN_PATH` for every herdr invocation (fallback `herdr`) and `HERDR_PLUGIN_ID` for the plugin pane open.
- Read the theme from `$XDG_CONFIG_HOME/herdr/config.toml` when set, else `~/.config/herdr/config.toml`.
- Cap scrollback reads at 5000 lines per pane (was one million).
- Standalone repository: install via `herdr plugin install`, removed monorepo references, added CI, LICENSE, SECURITY and CONTRIBUTING.
- Document the raw-socket exact focus, privacy behavior and optional dependencies (fd, rg, lazygit, editor).
- Manifest: version 0.2.0, `min_herdr_version` 0.9.5.
- Tests: no hardcoded temp directory; added tests for binary path, plugin id and config path.

## 0.1.0

- Initial release: fuzzy terminal finder with exact focus, scrollback search and file/folder/ripgrep/lazygit pickers.

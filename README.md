# herdr-find

Fuzzy-find and jump to any terminal, agent or shell in your HerdR session, including text inside their scrollback.

```text

◆ HERDR FIND  |  2 / 2 terminals
/
────────────────────────────────────────
  [CX] Build API                 working
› [SH] Shell 界 café               shell










Shell 界 café
Work / Project / w1:p2 | /example
j/k move  / search  Enter focus  f file…
```

(Synthetic preview; see [docs/PREVIEW.txt](docs/PREVIEW.txt) for wider layouts.)

## Features

- Fuzzy search over titles, workspace/tab labels, agent type, working directory and recent terminal output.
- Keyboard-first, vim-style navigation: opens in navigation mode, `/` to type a query.
- Exact focus of the chosen pane, then the popup closes.
- Optional file, folder and ripgrep content search rooted at the selected terminal's directory, with preview, clipboard copy, editor and lazygit launch.
- Standard-library Python only: no pip packages, no build step.

## Why not the built-in workspace picker?

HerdR's built-in picker navigates workspaces. herdr-find searches every terminal pane across all workspaces and tabs at once, ranks results with a fuzzy subsequence scorer, matches against pane scrollback as well as titles, and distinguishes coding agents from ordinary shells.

## Requirements

- HerdR 0.9.5 or newer
- Python 3.9+ available as `python3`
- Linux or macOS

## Install

```sh
herdr plugin install carlosiborra/herdr-find
```

Bind it in your HerdR `config.toml` (apply this yourself):

```toml
[[keys.command]]
key = "prefix+f"
type = "plugin_action"
command = "herdr-find.open"
description = "fuzzy find any terminal"
```

Then run `herdr config check` and `herdr server reload-config`. You can also open it directly with `herdr plugin action invoke herdr-find.open`.

## Usage

- `/` or `i`: type a query (titles, labels, terminal content, agent type, cwd).
- `j`/`k` or arrows: move. While typing, use Ctrl-N/Ctrl-P or arrows.
- `Enter` while typing: keep the query and return to selection. `Enter` in navigation: focus the selected pane and exit.
- `Esc`: leave query entry; `Esc` or `q` in navigation closes. `Ctrl-C` closes immediately.
- `Ctrl-R`: discard and reread scrollback.

Matching is case-insensitive subsequence matching favoring consecutive letters and word boundaries. The finder's own pane is excluded. `--poll SECONDS` changes the snapshot interval (500 ms floor).

Resource keys (in navigation, with a terminal selected):

| Key | Action |
| --- | --- |
| `f` / `d` / `s` | Files / folders / ripgrep text in the terminal's directory |
| `Enter` | Enter folder or open file in editor |
| `o` | Open with the default app (`open` on macOS, `xdg-open` on Linux) |
| `y` / `Y` | Copy absolute path / file URI (system clipboard) |
| `g` | Launch lazygit at the selected repository |
| `h` / `l` | Parent / enter directory |
| `r` | Refresh |
| `t`, `q`, `Esc` | Back to the terminal picker |

## Optional dependencies

Terminal search needs nothing beyond Python. These are used only by the resource keys and degrade gracefully: if a tool is missing, the picker shows a short error and stays open.

- [`fd`](https://github.com/sharkdp/fd) for `f` and `d` (Debian and Ubuntu install it as `fdfind`, which is detected automatically)
- [`rg`](https://github.com/BurntSushi/ripgrep) for `s`
- [`lazygit`](https://github.com/jesseduffield/lazygit) for `g`
- An editor from `$VISUAL` or `$EDITOR` (fallback: the first of `nvim`, `vim`, `vi` on `PATH`) for opening files
- A clipboard tool for `y`/`Y`: `pbcopy` on macOS; `wl-copy` (Wayland), `xclip` or `xsel` (X11) on Linux
- The system opener for `o`: `open` on macOS, `xdg-open` on Linux

## Privacy and trust

HerdR plugins are not sandboxed; this one runs with your user's permissions. What it does:

- Runs `$HERDR_BIN_PATH` (fallback `herdr`): `api snapshot`, `pane read` and `plugin pane open`.
- Reads each pane's recent scrollback locally (at most 5000 lines per pane, 2-second timeout) to match your query. Scrollback is held in memory for the popup's lifetime and is never stored, logged or sent anywhere.
- Reads `$XDG_CONFIG_HOME/herdr/config.toml` (else `~/.config/herdr/config.toml`) only for `[theme.custom]` colors.
- Connects to the `HERDR_SOCKET_PATH` Unix socket to send one `pane.focus` request. The HerdR CLI has no generic API-call command and `herdr pane focus` is directional only, so exact focus of an arbitrary pane uses the raw socket. It never guesses a socket path or uses another session.
- Only on explicit keypress: runs `fd`, `rg`, `git`, `lazygit`, your editor, the system opener or a clipboard tool on the selected terminal's directory or file. Arguments are passed as argv, never through a shell.
- Makes no network connections, writes no files, keeps no search history and injects no terminal input.

## Scrollback search

Once a query is entered, each other terminal is read once (sequentially, `recent-unwrapped`, up to 5000 lines) and matched alongside titles. The best matching line is shown with surrounding context. Coverage depends on HerdR's retained scrollback; alternate-screen or older content may be unavailable, and unavailable panes are reported. New output requires Ctrl-R.

## Update and uninstall

```sh
herdr plugin update
herdr plugin uninstall herdr-find
```

Remove the keybinding from your config as well.

## Development and tests

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src bin
PYTHONPATH=src python3 tests/render_snapshots.py
```

Tests use synthetic snapshots, an injected CLI runner, a temporary Unix socket stub and a PTY with a fake client; they never contact a real HerdR server. See [CONTRIBUTING.md](CONTRIBUTING.md), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/VERIFICATION.md](docs/VERIFICATION.md).

## License

MIT. See [LICENSE](LICENSE).

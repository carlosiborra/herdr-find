# Contributing

Find is a standalone Python standard-library plugin. It loads source when the popup starts and needs no pip packages, fzf or binary build step. Run checks from the repository root using Python 3.9 or later.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
python3 -m compileall -q src bin
python3 -m py_compile bin/herdr-find
PYTHONPATH=src python3 tests/render_snapshots.py
git diff --check
```

The separate `py_compile` command covers the extensionless entrypoint. Unit tests use synthetic snapshots, an injected CLI runner, a temporary AF_UNIX stub and a fake-client PTY. They do not inspect a live HerdR session. Snapshot output is synthetic and suitable for review.

## Change boundaries

Preserve pure model and renderer functions. Cover query edits, ranking ties, disappearing selection, empty results, agents and shells, malformed snapshots, Unicode and small terminals. Exact focus must require the inherited socket and verify both response ID and destination. Never search for or fall back to another session's socket.

Keep a single worker, a 500 ms polling floor, bounded I/O, generic errors and last-good records on failure. No unrequested directory scans, input injection, new Python dependencies, search history, notifications or data persistence belong in this plugin.

The terminal/text/theme/search helpers are vendored source files that originated from a shared helper set; they are maintained here independently.

These files (`theme.py`, `terminal.py`, `search.py`, `text.py`) are guarded by `tests/test_vendored.py`, which compares their sha256 to a recorded table. Change them only deliberately: update the hash in that test and mention the change in `CHANGELOG.md`.

Scrollback reads are capped at 5000 lines per pane (`SCROLLBACK_LINES` in `client.py`); keep every herdr invocation going through `HERDR_BIN_PATH` and the plugin id from `HERDR_PLUGIN_ID`.

## Pull requests

Describe the change and the tests you ran. Use synthetic frames instead of real titles, paths, pane output, session IDs, config or raw diagnostics. For native checks, follow [verification](docs/VERIFICATION.md) inside a real HerdR pane; do not set HERDR_ENV by hand.

Contributions are accepted under the repository's MIT license (see the root `LICENSE`).

Resource tests use temporary synthetic directories and the installed fd/rg/Git tools. Clipboard and interactive app launches use injected runners to avoid altering the developer clipboard or opening applications. The resource PTY test exercises files, real fixture previews, mode return and terminal restoration.

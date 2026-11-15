# Verification and troubleshooting

This guide describes how version 0.2.0 is tested and how to troubleshoot it.

## Test coverage (version 0.2.0)

| Surface | Observed result |
| --- | --- |
| Unit and PTY suite | 29 tests pass on macOS (Python 3.15 locally); CI runs them on Linux and macOS with Python 3.9 and 3.13 |
| Compilation | src/bin compileall and extensionless entrypoint py_compile pass |
| Rendering | Synthetic frames printed at 40/80/160 columns; small dimensions/control checks pass |
| Data fixtures | Agents, ordinary shells, own-pane exclusion, Unicode, invalid data and query selection covered |
| Exact focus | Temporary AF_UNIX stub validates request, split response and destination checks |
| Installed API contract | Herdr 0.9.5 schema includes pane.focus; CLI focus is directional |
| Native socket response/focus | Manual check, see below |
| Linux native popup and newer Herdr versions | Not tested (unit tests run in CI) |

PTY tests exercise typing, shell selection/focus calls, Escape/Ctrl-C, SIGINT/SIGTERM, resize, outage recovery and unexpected errors with fake session data. They compare terminal settings with macOS's PENDIN state bit normalized. A successful stub response does not establish real server compatibility.

## Native evaluation

Use a genuine Herdr-managed terminal with its inherited environment. Do not set HERDR_ENV manually, guess sockets or fall back to a different session. Install the plugin and apply an unused binding using the [README](../README.md).

1. Record `herdr --version`, `python3 --version` and `herdr config check` outcome without saving configuration contents.
2. Invoke `herdr plugin action invoke carlosiborra.find.open`. Confirm the centered popup opens and includes expected agents and ordinary shells while excluding its own pane.
3. Type a title subsequence, then try workspace/tab, type and cwd fragments. Confirm the first result is selected after editing, arrows change selection and backspace edits the query.
4. Choose an ordinary shell and press Enter. Confirm the popup closes and the exact shell is focused. Repeat with a coding agent and verify the selected destination again.
5. Resize around 40, 80 and 160 columns while filtering. Confirm query and selection survive and details remain bounded.
6. Use a query with no match, press Enter and confirm no focus occurs. Escape/Ctrl-C must close normally and restore the original terminal.
7. Reopen and verify the previous query is absent. Confirm there are no search history or terminal-data files created by Find.

Stop if focus selects the wrong pane, the socket response cannot be confirmed, or terminal cleanup fails. Close only the plugin-owned popup and report which step failed, without pasting private terminal content. Do not disrupt the session server or agents to simulate failures; the local tests cover retries.

## Troubleshooting

| Symptom | Check or action |
| --- | --- |
| Must run inside a Herdr-managed session | Launch from Herdr; do not set HERDR_* variables by hand |
| Binding does nothing | Check that the plugin is installed, carlosiborra.find.open action, unused key and config reload |
| Focus unavailable | Confirm Herdr inherited HERDR_SOCKET_PATH, selected pane still exists and your Herdr version supports `pane.focus` (0.9.5+) |
| Results are stale with an error | Last-good records stay visible; polling retries rather than clearing results |
| A typed q does not close | All printable keys search; use Escape or Ctrl-C |
| Matching differs from fzf | Expected: a small deterministic subsequence scorer is bundled |
| Own pane appears | Own-pane exclusion requires inherited HERDR_PANE_ID; report missing context without dumping environment |
| Terminal damaged after force-kill | In the affected shell, run `stty sane` and `reset`; SIGKILL bypasses cleanup |

## Reporting results

When reporting a problem, include the revision (`git rev-parse HEAD`), OS, Herdr and Python versions, test results and which native step failed. Agent and shell counts help; leave out raw snapshots, socket paths, environment dumps, titles, working directories, commands, output and session IDs. Use the synthetic previews for screenshots.

Native checks on Linux and Herdr versions newer than 0.9.5 remain unverified. CI runs the unit tests (not the native steps) on Linux and macOS.

To check content search, search a known phrase present only in terminal output, confirm its matching snippet and source focus, then append output and use Ctrl-R to refresh. Confirm unavailable reads remain visible in coverage. Older or application-owned history may be unavailable.

To check resource search, select a terminal with a known directory, press Escape then f/d/s, and verify the root breadcrumb. Search a known file and rg phrase, inspect contextual preview, copy path/link with y/Y, enter/leave a folder with l/h, and return with t. Open a harmless file in the editor and launch lazygit on a known repository. Check that lazygit receives the expected root and no Git action runs automatically. The automated tests cover clipboard and editor/lazygit only with fakes; this manual procedure covers the real behavior.

Selection-first behavior: both terminal and resource searches open in navigation. Press /, type a known query and Enter once. Confirm the popup stays open with the same query, use j/k to choose, then Enter again to focus/open. Enter from typing with zero results still leaves typing and performs no action.

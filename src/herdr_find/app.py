"""Live all-terminal finder with one worker and memory-only state."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import math
import os
from pathlib import Path
import sys
import time

from .client import Client, FindError
from .model import parse_snapshot, matches
from .renderer import render
from .terminal import Terminal, TerminalExit
from .theme import Palette, color_mode, read_colors
from . import resources


class Finder:
    def __init__(self):
        self.records = ()
        self.query = self.selected = self.error = self.notice = ''
        self.content = {}
        self._match_key = None
        self._matches = ()
        self.filtering = False

    def rows(self):
        key = (self.records, self.query, tuple((p, id(lines)) for p, lines in self.content.items()))
        if key != self._match_key:
            self._matches = matches(self.records, self.query, self.content)
            self._match_key = key
        return self._matches

    def reconcile(self):
        rows = self.rows()
        if self.selected not in {r.pane_id for r in rows}:
            self.selected = rows[0].pane_id if rows else ''

    def handle(self, key):
        self.notice = ''
        if key == 'interrupt':
            return ('quit', '')
        if key == 'escape':
            if self.filtering:
                self.filtering = False
                return None
            return ('quit', '')
        if not self.filtering and key in ('/', 'i'):
            self.filtering = True
            return None
        if not self.filtering and key == 'q':
            return ('quit', '')
        rows = self.rows()
        if not self.filtering and key in ('f', 'd', 's', 'g'):
            record = next((r for r in rows if r.pane_id == self.selected), None)
            if record and record.cwd:
                return ('resources', {'f': 'files', 'd': 'folders', 's': 'text', 'g': 'git'}[key], record.cwd)
            self.notice = 'Select a terminal with a directory first'
            return None
        if key == 'enter':
            if self.filtering:
                self.filtering = False
            if self.selected:
                return ('focus', self.selected)
        direction = ('down' if key == '\x0e' or (not self.filtering and key == 'j') else
                     'up' if key == '\x10' or (not self.filtering and key == 'k') else key)
        if direction in ('up', 'down') and rows:
            index = next((i for i, r in enumerate(rows) if r.pane_id == self.selected), 0)
            index = min(len(rows) - 1, max(0, index + (1 if direction == 'down' else -1)))
            self.selected = rows[index].pane_id
        elif self.filtering and key == 'backspace':
            self.query = self.query[:-1]
            self.selected = ''
        elif self.filtering and len(key) == 1 and key.isprintable():
            self.query += key
            self.selected = ''
        self.reconcile()
        return None


def run(client, terminal, palette, own_pane, interval):
    state = Finder()
    previous, size = (), None
    next_poll = 0
    future, operation, queued = None, '', None
    reading = ''
    attempted = set()
    unavailable = set()
    worker = ThreadPoolExecutor(max_workers=1)
    try:
        while True:
            now = time.monotonic()
            if future is not None and future.done():
                try:
                    result = future.result()
                    if operation == 'focus':
                        return 0
                    if operation == 'read':
                        if reading in {r.pane_id for r in state.records}:
                            state.content[reading] = result
                            state._match_key = None
                    else:
                        state.records = parse_snapshot(result, own_pane)
                        live = {r.pane_id for r in state.records}
                        state.content = {p: lines for p, lines in state.content.items() if p in live}
                        attempted.intersection_update(live)
                        unavailable.intersection_update(live)
                    state.reconcile()
                    state.error = ''
                except (FindError, ValueError):
                    if operation == 'read':
                        unavailable.add(reading)
                    else:
                        state.error = 'Focus unavailable; retry selection' if operation == 'focus' else 'HerdR unavailable; retrying'
                future = None
            if future is None:
                if queued:
                    operation = 'focus'
                    future = worker.submit(client.focus, queued)
                    queued = None
                elif now >= next_poll:
                    operation = 'snapshot'
                    future = worker.submit(client.snapshot)
                    next_poll = now + interval
                elif state.query or state.selected:
                    candidates = state.records if state.query else tuple(
                        r for r in state.records if r.pane_id == state.selected)
                    reading = next((r.pane_id for r in candidates if r.pane_id not in attempted), '')
                    if reading:
                        attempted.add(reading)
                        operation = 'read'
                        future = worker.submit(client.read, reading)
            current_size = terminal.size()
            if size != current_size:
                size, previous = current_size, ()
                terminal.write('\x1b[2J')
            coverage = ('Scrollback: %d/%d read, %d unavailable | Ctrl-R refresh' %
                        (len(state.content), len(state.records), len(unavailable)))
            frame = render(state.rows(), state.query, state.selected, *size, palette,
                           error=state.error or state.notice, total=len(state.records), coverage=coverage,
                           filtering=state.filtering)
            changed = [(i, line) for i, line in enumerate(frame) if i >= len(previous) or previous[i] != line]
            if changed:
                terminal.write(''.join('\x1b[%d;1H\x1b[0m\x1b[2K%s' % (i + 1, line) for i, line in changed))
            previous = frame
            for key in terminal.keys():
                if key == '\x12':
                    attempted.clear()
                    unavailable.clear()
                    state.content.clear()
                    state._match_key = None
                    state.reconcile()
                    continue
                action = state.handle(key)
                if action:
                    if action[0] == 'resources':
                        return action
                    if action[0] == 'quit':
                        return 130 if key == 'interrupt' else 0
                    queued = action[1]
    finally:
        state.records = ()
        state.content.clear()
        state._matches = ()
        state.query = state.selected = ''
        if future:
            future.cancel()
        worker.shutdown(wait=False, cancel_futures=True)


def config_path(env):
    base = env.get('XDG_CONFIG_HOME')
    root = Path(base) if base else Path.home() / '.config'
    return root / 'herdr' / 'config.toml'


def main(argv=None, environ=None, client=None):
    env = dict(os.environ if environ is None else environ)
    parser = argparse.ArgumentParser(description='Fuzzy search all HerdR terminals')
    parser.add_argument('--open', action='store_true', help='Launch the plugin overlay')
    parser.add_argument('--poll', type=float, default=1, help='Polling seconds, minimum 0.5')
    args = parser.parse_args(argv)
    if env.get('HERDR_ENV') != '1':
        print('HerdR Find must run inside a HerdR-managed session.', file=sys.stderr)
        return 2
    client = client or Client(env.get('HERDR_BIN_PATH') or 'herdr', env.get('HERDR_SOCKET_PATH'),
                              plugin_id=env.get('HERDR_PLUGIN_ID') or 'herdr-find')
    if args.open:
        try:
            client.open()
            return 0
        except FindError:
            print('HerdR Find could not open its search pane.', file=sys.stderr)
            return 1
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('HerdR Find requires an interactive terminal.', file=sys.stderr)
        return 2
    interval = max(0.5, args.poll) if math.isfinite(args.poll) else 1
    palette = Palette(color_mode(env), read_colors(config_path(env)))
    try:
        with Terminal(sys.stdin, sys.stdout) as terminal:
            while True:
                outcome = run(client, terminal, palette, env.get('HERDR_PANE_ID', ''), interval)
                if not isinstance(outcome, tuple):
                    return outcome
                _, mode, root = outcome
                if mode == 'git':
                    outcome = ('git', resources.Tools().git_root(Path(root)))
                else:
                    outcome = resources.run(root, mode, terminal, palette)
                if outcome[0] == 'terminals':
                    continue
                if outcome[0] == 'quit':
                    return 130
                break
        # Restore raw mode and the alternate screen before handing over this popup.
        resources.launch(outcome, env)
        return 0
    except resources.ResourceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except TerminalExit as exc:
        return 128 + exc.signum
    except KeyboardInterrupt:
        return 130
    except Exception:
        print('HerdR Find stopped after an unexpected error.', file=sys.stderr)
        return 1

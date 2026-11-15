"""Directory-scoped file, folder and ripgrep picker with explicit user actions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

from .search import fuzzy_score
from .text import fit


class ResourceError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    path: Path
    line: int = 0
    text: str = ''

    @property
    def key(self):
        return (str(self.path), self.line)


def clipboard_command(env=None, which=shutil.which):
    """Pick a clipboard writer: pbcopy (macOS), wl-copy (Wayland), xclip or xsel (X11)."""
    env = env if env is not None else {}
    if which('pbcopy'):
        return ['pbcopy']
    if env.get('WAYLAND_DISPLAY') and which('wl-copy'):
        return ['wl-copy']
    if which('xclip'):
        return ['xclip', '-selection', 'clipboard']
    if which('xsel'):
        return ['xsel', '--clipboard', '--input']
    if which('wl-copy'):
        return ['wl-copy']
    return None


def opener_command(platform=None):
    """System opener: `open` on macOS, `xdg-open` elsewhere (Linux `open` is unrelated)."""
    return 'open' if (platform or sys.platform) == 'darwin' else 'xdg-open'


def editor_command(env, which=shutil.which):
    """$VISUAL, then $EDITOR, then the first of nvim, vim, vi on PATH."""
    configured = env.get('VISUAL') or env.get('EDITOR')
    if configured:
        return shlex.split(configured)
    for name in ('nvim', 'vim', 'vi'):
        if which(name):
            return [name]
    return []


def fd_binary(which=shutil.which):
    """Return the fd executable name; Debian and Ubuntu install it as fdfind."""
    if which('fd') is None and which('fdfind') is not None:
        return 'fdfind'
    return 'fd'


class Tools:
    def __init__(self, runner=subprocess.run, fd=None, clipboard=None):
        self.runner = runner
        self.fd = fd or fd_binary()
        self.clipboard = clipboard

    def call(self, args, root, accepted=(0,)):
        try:
            result = self.runner(list(args), cwd=str(root), capture_output=True,
                                 text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ResourceError('Tool unavailable or timed out; narrow the directory or retry') from exc
        if result.returncode not in accepted:
            raise ResourceError('Tool failed; check the directory and retry')
        return result

    def scan(self, root, mode, query):
        if mode == 'text':
            if not query:
                return (), 'Type text to search with rg'
            result = self.call(('rg', '--json', '--fixed-strings', '--smart-case',
                                '--max-count', '20', '--max-columns', '500',
                                '--', query, '.'), root, accepted=(0, 1))
            entries = []
            limited = False
            try:
                for line in result.stdout.splitlines():
                    event = json.loads(line)
                    if event.get('type') != 'match':
                        continue
                    data = event['data']
                    name = data['path'].get('text')
                    text = data['lines'].get('text')
                    if name is None or text is None:
                        limited = True
                        continue
                    if len(entries) >= 500:
                        limited = True
                        break
                    entries.append(Entry(root / name, data['line_number'], text.rstrip('\n')))
            except (ValueError, KeyError, TypeError) as exc:
                raise ResourceError('Invalid rg result') from exc
            partial = limited or result.returncode == 0 and bool(result.stderr.strip())
            return tuple(entries), ('Partial results | ' if partial else '') + 'rg text | up to 500 results, 20 matches/file'
        result = self.call((self.fd, '--type', 'd' if mode == 'folders' else 'f',
                            '--absolute-path', '--print0', '--max-results', '5000',
                            '--exclude', '.git', '.', str(root)), root)
        names = [name for name in result.stdout.split('\0') if name]
        scored = []
        for index, name in enumerate(names):
            path = Path(name)
            score = fuzzy_score(query, str(path.relative_to(root)))
            if score is not None:
                scored.append((score, index, Entry(path)))
        rows = tuple(item[2] for item in sorted(scored, key=lambda item: item[:2])[:500])
        return rows, ('Partial listing | ' if len(names) >= 5000 or len(scored) > 500 else '') + 'fd paths | ignores respected'

    def preview(self, entry):
        try:
            if entry.path.is_dir():
                import itertools
                names = list(itertools.islice(entry.path.iterdir(), 30))
                return tuple(p.name + ('/' if p.is_dir() else '') for p in sorted(names))
            with entry.path.open('rb') as stream:
                data = stream.read(256 * 1024)
            if b'\0' in data:
                return ('Binary file',)
            lines = data.decode('utf-8', errors='replace').splitlines()
            position = max(0, entry.line - 1)
            if position >= len(lines):
                return (entry.text, 'Context beyond 256 KiB preview limit')
            return tuple(('%s %d ' % ('>' if i == position and entry.line else ' ', i + 1)) + lines[i]
                         for i in range(max(0, position - 3), min(len(lines), position + 6)))
        except OSError:
            return ('Preview unavailable',)

    def copy(self, entry, link=False):
        value = entry.path.absolute().as_uri() + ('#L%d' % entry.line if entry.line else '') if link else str(entry.path)
        command = clipboard_command(dict(os.environ)) if self.clipboard is None else self.clipboard
        if not command:
            raise ResourceError('Clipboard unavailable; install pbcopy, wl-copy, xclip or xsel')
        try:
            result = self.runner(command, input=value, text=True, capture_output=True,
                                 timeout=2, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ResourceError('Clipboard unavailable') from exc
        if result.returncode:
            raise ResourceError('Clipboard unavailable')

    def git_root(self, root):
        result = self.call(('git', '-C', str(root), 'rev-parse', '--show-toplevel'), root)
        path = Path(result.stdout.strip())
        if not path.is_dir():
            raise ResourceError('Repository unavailable')
        return path


class Picker:
    def __init__(self, root, mode='files'):
        self.root = Path(root).resolve()
        self.mode, self.query = mode, ''
        self.filtering = False
        self.entries, self.selected = (), None
        self.preview, self.message = (), ''
        self.version = 0

    def current(self):
        return next((entry for entry in self.entries if entry.key == self.selected), None)

    def update(self, entries):
        self.entries = entries
        if self.selected not in {e.key for e in entries}:
            self.selected = entries[0].key if entries else None

    def change(self):
        self.version += 1
        self.entries, self.selected, self.preview = (), None, ()

    def handle(self, key):
        if key == 'interrupt':
            return ('quit',)
        if key == 'enter' and self.filtering:
            self.filtering = False
            return None
        if key == 'escape':
            if self.filtering:
                self.filtering = False
                return None
            return ('terminals',)
        if not self.filtering:
            if key in ('q', 't'):
                return ('terminals',)
            if key in ('/', 'i'):
                self.filtering = True
                return None
            if key in ('f', 'd', 's'):
                self.mode = {'f': 'files', 'd': 'folders', 's': 'text'}[key]
                self.query = ''
                self.change()
                return None
            if key == 'h':
                self.root = self.root.parent
                self.query = ''
                self.change()
                return None
            if key == 'r':
                self.change()
                return None
            if key == 'g':
                entry = self.current()
                root = entry.path if entry and entry.path.is_dir() else entry.path.parent if entry else self.root
                return ('git', root)
            if key in ('y', 'Y', 'o') and self.current():
                return ({'y': 'copy', 'Y': 'link', 'o': 'open'}[key], self.current())
        direction = 'down' if key == '\x0e' or not self.filtering and key == 'j' else 'up' if key == '\x10' or not self.filtering and key == 'k' else key
        if direction in ('up', 'down') and self.entries:
            index = next((i for i, e in enumerate(self.entries) if e.key == self.selected), 0)
            index = max(0, min(len(self.entries) - 1, index + (1 if direction == 'down' else -1)))
            self.selected = self.entries[index].key
            self.preview = ()
        elif key == 'enter' or not self.filtering and key == 'l':
            entry = self.current()
            if entry and entry.path.is_dir():
                self.root, self.query = entry.path, ''
                self.change()
            elif entry and key == 'enter':
                return ('edit', entry)
        elif self.filtering and (key == 'backspace' or len(key) == 1 and key.isprintable()):
            self.query = self.query[:-1] if key == 'backspace' else self.query + key
            self.change()
        return None


def render(state, width, height, palette):
    width, height = max(1, width), max(1, height)
    lines = [palette.paint(fit('FIND  |  FILES [f]  FOLDERS [d]  RG TEXT [s]  |  ' + state.mode.upper(), width, True), 'accent', bold=True),
             palette.paint(fit(str(state.root), width, True), 'subtext0'),
             palette.paint(fit('/ ' + state.query + ('▏' if state.filtering else ''), width, True), 'blue'),
             palette.paint(fit(state.message, width, True), 'subtext0')]
    preview_height = min(10, height // 3) if height >= 12 else 0
    body_height = max(0, height - len(lines) - preview_height - 1)
    index = next((i for i, e in enumerate(state.entries) if e.key == state.selected), 0)
    offset = max(0, index - body_height + 1)
    for entry in state.entries[offset:offset + body_height]:
        active = entry.key == state.selected
        name = str(entry.path.relative_to(state.root))
        text = ('› ' if active else '  ') + name + (':%d  %s' % (entry.line, entry.text) if entry.line else '')
        lines.append(palette.paint(fit(text, width, True), 'text', active, active))
    if not state.entries and body_height:
        lines.append(palette.paint(fit('No results' if state.query else 'Type a query or choose a mode', width, True), 'subtext0'))
    while len(lines) < height - preview_height - 1:
        lines.append(' ' * width)
    if preview_height:
        lines.append(palette.paint(fit('── PREVIEW ' + '─' * width, width), 'accent'))
        lines.extend(palette.paint(fit(line, width, True), 'accent' if line.startswith('>') else 'text')
                     for line in state.preview[:preview_height - 1])
    while len(lines) < height - 1:
        lines.append(' ' * width)
    footer = ('Type query  Ctrl-N/P select  Enter select  Esc navigate' if state.filtering else
              'j/k move  / query  f/d/s modes  h/l dirs  Enter edit  o open  y path  Y link  g lazygit  t back')
    lines.append(palette.paint(fit(footer, width, True), 'subtext0'))
    return tuple(lines[:height] + [' ' * width] * max(0, height - len(lines)))


def run(root, mode, terminal, palette, tools=None):
    tools = tools or Tools()
    state = Picker(root, mode)
    if not state.root.is_dir():
        raise ResourceError('Selected terminal directory is unavailable')
    worker = ThreadPoolExecutor(max_workers=1)
    future, operation, version, selection = None, '', -1, None
    scanned, previewed, due = -1, None, 0
    previous, size = (), None
    try:
        while True:
            now = time.monotonic()
            if future is not None and future.done():
                try:
                    result = future.result()
                    if version == state.version:
                        if operation == 'scan':
                            state.update(result[0])
                            state.message = result[1]
                        elif operation == 'preview' and selection == state.selected:
                            state.preview = result
                        elif operation == 'copy':
                            state.message = 'Copied path/link'
                        elif operation == 'git':
                            return ('git', result)
                except ResourceError as exc:
                    if version == state.version:
                        state.message = str(exc)
                future = None
            if future is None:
                if scanned != state.version and now >= due:
                    scanned = version = state.version
                    operation = 'scan'
                    future = worker.submit(tools.scan, state.root, state.mode, state.query)
                elif state.current() and previewed != (state.version, state.selected):
                    version, selection = state.version, state.selected
                    previewed = (version, selection)
                    operation = 'preview'
                    future = worker.submit(tools.preview, state.current())
            current_size = terminal.size()
            if current_size != size:
                size, previous = current_size, ()
                terminal.write('\x1b[2J')
            frame = render(state, *size, palette)
            terminal.write(''.join('\x1b[%d;1H\x1b[0m\x1b[2K%s' % (i + 1, line)
                                   for i, line in enumerate(frame) if i >= len(previous) or previous[i] != line))
            previous = frame
            for key in terminal.keys():
                old_version = state.version
                action = state.handle(key)
                if state.version != old_version:
                    due = time.monotonic() + 0.15
                    state.message = 'Searching…'
                if not action:
                    continue
                if action[0] in ('quit', 'terminals', 'edit', 'open'):
                    return action
                if future is not None:
                    state.message = 'Search/preview in progress; retry the action'
                    continue
                version = state.version
                if action[0] == 'git':
                    operation = 'git'
                    future = worker.submit(tools.git_root, action[1])
                else:
                    operation = 'copy'
                    future = worker.submit(tools.copy, action[1], action[0] == 'link')
    finally:
        if future:
            future.cancel()
        worker.shutdown(wait=True, cancel_futures=True)


def launch(action, env, runner=subprocess.run, platform=None):
    kind, value = action
    if kind == 'git':
        args, root = ['lazygit'], value
    elif kind == 'open':
        args, root = [opener_command(platform), str(value.path)], value.path.parent
    else:
        editor = editor_command(env)
        if not editor:
            raise ResourceError('Editor is not configured')
        args = editor + (['+%d' % value.line] if value.line else []) + ['--', str(value.path)]
        root = value.path.parent
    try:
        result = runner(args, cwd=str(root), check=False)
    except OSError as exc:
        raise ResourceError('Selected app is unavailable') from exc
    if result.returncode:
        raise ResourceError('Selected app exited with an error')

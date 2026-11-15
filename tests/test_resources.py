import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from herdr_find.resources import Entry, Picker, Tools, ResourceError, clipboard_command, editor_command, fd_binary, opener_command, render, launch, run

HAS_FD_RG = bool((shutil.which('fd') or shutil.which('fdfind')) and shutil.which('rg'))
from herdr_find.theme import Palette
from herdr_find.text import cell_width


class ResourceTests(unittest.TestCase):
    def test_picker_scan_preview_copy_and_return_execute_on_worker(self):
        import time
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            calls = []
            class Tools:
                def scan(self, root, mode, query):
                    calls.append(('scan', mode))
                    return ((Entry(root / 'file.txt'),), 'complete')
                def preview(self, entry):
                    calls.append(('preview', entry.path.name))
                    return ('preview fixture',)
                def copy(self, entry, link):
                    calls.append(('copy', entry.path.name, link))
            class Terminal:
                output = ''
                copied = False
                ticks = 0
                def size(self):
                    return (100, 24)
                def write(self, text):
                    self.output += text
                def keys(self):
                    self.ticks += 1
                    if self.ticks > 500:
                        raise AssertionError('Picker did not complete')
                    time.sleep(0.001)
                    if 'preview fixture' in self.output and not self.copied:
                        self.copied = True
                        return ('Y',)
                    if 'Copied path/link' in self.output:
                        return ('t',)
                    return ()
            self.assertEqual(run(root, 'files', Terminal(), Palette(mode='none'), Tools()), ('terminals',))
            self.assertEqual(calls, [('scan', 'files'), ('preview', 'file.txt'), ('copy', 'file.txt', True)])

    def test_cross_platform_clipboard_opener_and_editor(self):
        def only(*names):
            return lambda name: '/bin/' + name if name in names else None
        self.assertEqual(clipboard_command({}, only('pbcopy', 'xclip')), ['pbcopy'])
        self.assertEqual(clipboard_command({'WAYLAND_DISPLAY': 'wayland-0'}, only('wl-copy', 'xclip')), ['wl-copy'])
        self.assertEqual(clipboard_command({}, only('wl-copy', 'xclip')), ['xclip', '-selection', 'clipboard'])
        self.assertEqual(clipboard_command({}, only('xsel')), ['xsel', '--clipboard', '--input'])
        self.assertIsNone(clipboard_command({}, only()))
        self.assertEqual(opener_command('darwin'), 'open')
        self.assertEqual(opener_command('linux'), 'xdg-open')
        self.assertEqual(editor_command({'EDITOR': 'code --wait'}, only()), ['code', '--wait'])
        self.assertEqual(editor_command({}, only('vim', 'vi')), ['vim'])
        self.assertEqual(editor_command({}, only()), [])
        with self.assertRaises(ResourceError) as raised:
            Tools(clipboard=False).copy(Entry(Path('/example/f')))
        self.assertIn('Clipboard unavailable', str(raised.exception))
        sent = []
        Tools(runner=lambda args, **kw: sent.append((args, kw['input'])) or subprocess.CompletedProcess(args, 0),
              clipboard=['xclip', '-selection', 'clipboard']).copy(Entry(Path('/example/f')))
        self.assertEqual(sent, [(['xclip', '-selection', 'clipboard'], '/example/f')])

    def test_fd_binary_prefers_fd_then_debian_fdfind(self):
        self.assertEqual(fd_binary(lambda name: '/bin/fd' if name == 'fd' else None), 'fd')
        self.assertEqual(fd_binary(lambda name: '/bin/fdfind' if name == 'fdfind' else None), 'fdfind')
        self.assertEqual(fd_binary(lambda name: None), 'fd')

    @unittest.skipUnless(HAS_FD_RG, 'needs fd (or fdfind) and rg')
    def test_fd_files_folders_and_rg_content_on_real_temporary_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            folder = root / 'project space'
            folder.mkdir()
            file = folder / '-report.txt'
            file.write_text('before\nneedle: deployment rejected\nafter\n')
            tools = Tools()
            files, _ = tools.scan(root, 'files', 'rprt')
            self.assertEqual([e.path for e in files], [file])
            folders, _ = tools.scan(root, 'folders', 'prjsp')
            self.assertEqual([e.path for e in folders], [folder])
            hits, _ = tools.scan(root, 'text', 'deployment rejected')
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].path.resolve(), file)
            self.assertEqual(hits[0].line, 2)
            preview = '\n'.join(tools.preview(hits[0]))
            self.assertIn('before', preview)
            self.assertIn('> 2 needle', preview)
            self.assertIn('after', preview)
            self.assertEqual(tools.scan(root, 'text', 'absent')[0], ())

    def test_modal_selection_query_edit_directory_and_mode_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sub = root / 'folder'
            sub.mkdir()
            state = Picker(root)
            state.update((Entry(root / 'first'), Entry(sub)))
            self.assertFalse(state.filtering)
            state.handle('j')
            self.assertEqual(state.current().path, sub)
            state.handle('k')
            self.assertEqual(state.current().path, root / 'first')
            self.assertEqual(state.handle('y'), ('copy', Entry(root / 'first')))
            self.assertEqual(state.handle('Y'), ('link', Entry(root / 'first')))
            self.assertEqual(state.handle('enter'), ('edit', Entry(root / 'first')))
            state.handle('j')
            state.handle('l')
            self.assertEqual(state.root, sub)
            state.handle('s')
            self.assertEqual(state.mode, 'text')
            state.handle('/')
            state.handle('j')
            self.assertEqual(state.query, 'j')
            state.handle('escape')
            state.handle('h')
            self.assertEqual(state.root, root)
            self.assertEqual(state.handle('t'), ('terminals',))

    def test_clipboard_and_launch_are_structured_and_require_explicit_action(self):
        calls = []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, '', '')
        entry = Entry(Path('/example/repo/file name.py'), 14)
        Tools(runner, clipboard=['pbcopy']).copy(entry)
        self.assertEqual(calls[-1][1]['input'], '/example/repo/file name.py')
        Tools(runner, clipboard=['pbcopy']).copy(entry, link=True)
        self.assertEqual(calls[-1][1]['input'], 'file:///example/repo/file%20name.py#L14')
        launch(('edit', entry), {'EDITOR': 'nvim -u NONE'}, runner)
        self.assertEqual(calls[-1][0], ['nvim', '-u', 'NONE', '+14', '--', str(entry.path)])
        launch(('open', entry), {}, runner, platform='darwin')
        self.assertEqual(calls[-1][0], ['open', str(entry.path)])
        launch(('git', Path('/example/repo')), {}, runner)
        self.assertEqual(calls[-1][0], ['lazygit'])
        self.assertEqual(calls[-1][1]['cwd'], '/example/repo')
        self.assertTrue(all('shell' not in kwargs for _, kwargs in calls))

    def test_git_root_validation_missing_tools_and_timeouts(self):
        if shutil.which('git'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                subprocess.run(['git', 'init', '-q', str(root)], check=True)
                self.assertEqual(Tools().git_root(root).resolve(), root.resolve())
        def timeout(args, **kwargs):
            raise subprocess.TimeoutExpired(args, 5)
        with self.assertRaises(ResourceError):
            Tools(timeout).scan(Path('/example'), 'files', '')
        def unavailable(args, **kwargs):
            return subprocess.CompletedProcess(args, 1, '', 'private diagnostic')
        with self.assertRaises(ResourceError) as raised:
            Tools(unavailable).copy(Entry(Path('/example/file')))
        self.assertNotIn('private', str(raised.exception))

    def test_bounded_unicode_rendering_preview_and_empty_results(self):
        state = Picker('/example')
        state.update((Entry(Path('/example/界\x1b[2J.txt'), 2, 'result'),))
        state.preview = ('> 2 match\x1b[2J', 'surrounding context')
        for width in (1, 40, 80, 160):
            for height in (1, 4, 24, 34):
                frame = render(state, width, height, Palette(mode='none'))
                self.assertEqual(len(frame), height)
                self.assertTrue(all(cell_width(line) <= width for line in frame))
                self.assertNotIn('\x1b', '\n'.join(frame))
        self.assertIn('surrounding context', '\n'.join(render(state, 80, 24, Palette(mode='none'))))
        state.update(())
        self.assertIn('Type a query', '\n'.join(render(state, 80, 24, Palette(mode='none'))))

    def test_search_enter_never_edits_or_enters_a_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            folder = root / 'folder'; folder.mkdir()
            state = Picker(root)
            self.assertFalse(state.filtering)
            state.handle('/')
            state.handle('f')
            state.update((Entry(folder), Entry(root / 'file')))
            self.assertIsNone(state.handle('enter'))
            self.assertFalse(state.filtering)
            self.assertEqual(state.root, root)
            self.assertEqual(state.query, 'f')
            state.handle('j')
            self.assertEqual(state.handle('enter'), ('edit', Entry(root / 'file')))

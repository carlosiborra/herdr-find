import unittest
import time

from herdr_find.app import Finder, run
from herdr_find.client import FindError
from herdr_find.theme import Palette
from herdr_find.model import parse_snapshot
from test_find import snapshot


class AppTests(unittest.TestCase):
    def test_incremental_content_search_focus_and_failed_read_coverage(self):
        for fail in (False, True):
            calls = []
            class Client:
                def snapshot(self):
                    return snapshot()
                def read(self, target):
                    calls.append(('read', target))
                    if fail:
                        raise FindError('unavailable')
                    return ('needle in retained output',) if target == 'w1:p2' else ()
                def focus(self, target):
                    calls.append(('focus', target))
            class Terminal:
                output = ''
                ticks = 0
                typed = False
                def size(self):
                    return (100, 24)
                def write(self, text):
                    self.output += text
                def keys(self):
                    self.ticks += 1
                    if self.ticks > 500:
                        raise AssertionError('Content search did not complete')
                    time.sleep(0.001)
                    if not self.typed:
                        self.typed = True
                        return tuple('/needle')
                    if fail and '2 unavailable' in self.output:
                        return ('escape',)
                    if not fail and '> needle in retained output' in self.output:
                        return ('enter',)
                    return ()
            self.assertEqual(run(Client(), Terminal(), Palette(mode='none'), 'w1:p9', 1), 0)
            self.assertEqual([c for c in calls if c[0] == 'read'], [('read', 'w1:p1'), ('read', 'w1:p2')])
            self.assertEqual([c for c in calls if c[0] == 'focus'], [] if fail else [('focus', 'w1:p2')])

    def test_type_fuzzy_query_and_focus_shell(self):
        state = Finder()
        state.records = parse_snapshot(snapshot())
        state.reconcile()
        self.assertFalse(state.filtering)
        state.handle('/')
        for char in 'shl':
            state.handle(char)
        self.assertEqual(state.handle('enter'), ('focus', 'w1:p2'))
        self.assertFalse(state.filtering)
        self.assertEqual(state.query, 'shl')
        self.assertEqual(state.handle('escape'), ('quit', ''))

    def test_local_notice_survives_a_successful_poll(self):
        state = Finder()
        self.assertIsNone(state.handle('f'))
        self.assertEqual(state.notice, 'Select a terminal with a directory first')
        state.error = ''
        from herdr_find.renderer import render
        frame = ''.join(render(state.records, '', '', 80, 12, Palette(mode='none'),
                               error=state.error or state.notice))
        self.assertIn('Select a terminal', frame)
        state.handle('down')
        self.assertEqual(state.notice, '')

    def test_arrows_unicode_query_backspace_and_empty_results(self):
        state = Finder()
        state.records = parse_snapshot(snapshot())
        state.reconcile()
        state.handle('down')
        self.assertEqual(state.selected, 'w1:p2')
        state.handle('/')
        state.handle('界')
        self.assertEqual(state.selected, 'w1:p2')
        state.handle('backspace')
        self.assertEqual(state.selected, 'w1:p1')
        for char in '不存在':
            state.handle(char)
        self.assertEqual(state.selected, '')
        self.assertIsNone(state.handle('enter'))

    def test_vim_navigation_preserves_query_and_resumes_typing(self):
        state = Finder()
        state.records = parse_snapshot(snapshot())
        state.reconcile()
        self.assertFalse(state.filtering)
        state.handle('j')
        self.assertEqual(state.selected, 'w1:p2')
        state.handle('k')
        self.assertEqual(state.selected, 'w1:p1')
        self.assertEqual(state.query, '')
        state.handle('/')
        for char in 'shl':
            state.handle(char)
        state.handle('escape')
        self.assertEqual(state.query, 'shl')
        self.assertEqual(state.handle('enter'), ('focus', 'w1:p2'))

    def test_resource_actions_use_selected_terminal_directory(self):
        state = Finder()
        state.records = parse_snapshot(snapshot())
        state.reconcile()
        self.assertFalse(state.filtering)
        for key, mode in (('f', 'files'), ('d', 'folders'), ('s', 'text'), ('g', 'git')):
            self.assertEqual(state.handle(key), ('resources', mode, '/example'))

    def test_resource_app_launch_happens_after_terminal_restoration(self):
        from unittest.mock import patch
        from herdr_find.app import main
        from herdr_find.resources import Entry
        from pathlib import Path
        events = []
        class Terminal:
            def __init__(self, *args):
                pass
            def __enter__(self):
                events.append('enter')
                return self
            def __exit__(self, *args):
                events.append('restored')
        with patch('herdr_find.app.sys.stdin.isatty', return_value=True), \
             patch('herdr_find.app.sys.stdout.isatty', return_value=True), \
             patch('herdr_find.app.Terminal', Terminal), \
             patch('herdr_find.app.run', return_value=('resources', 'files', '/example')), \
             patch('herdr_find.app.resources.run', return_value=('edit', Entry(Path('/example/file')))), \
             patch('herdr_find.app.resources.launch', side_effect=lambda *args: events.append('launch')):
            self.assertEqual(main([], environ={'HERDR_ENV': '1'}, client=object()), 0)
        self.assertEqual(events, ['enter', 'restored', 'launch'])

    def test_enter_from_search_opens_the_selected_terminal(self):
        state = Finder()
        state.records = parse_snapshot(snapshot())
        state.reconcile()
        state.handle('/')
        self.assertEqual(state.handle('enter'), ('focus', 'w1:p1'))
        self.assertFalse(state.filtering)
        state.records = ()
        state.reconcile()
        state.handle('/')
        self.assertIsNone(state.handle('enter'))
        self.assertFalse(state.filtering)

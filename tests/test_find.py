import json
import socket
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from herdr_find.client import Client, FindError
from herdr_find.model import Terminal, parse_snapshot, matches
from herdr_find.renderer import render
from herdr_find.theme import Palette
from herdr_find.text import cell_width


def snapshot():
    return dict(workspaces=[dict(workspace_id='w1', label='Work')],
                tabs=[dict(tab_id='w1:t1', label='Project')],
                panes=[dict(pane_id='w1:p1', workspace_id='w1', tab_id='w1:t1',
                            terminal_title_stripped='Build API', agent='codex', agent_status='working', cwd='/example'),
                       dict(pane_id='w1:p2', workspace_id='w1', tab_id='w1:t1',
                            terminal_title_stripped='Shell 界 café', agent=None, agent_status='unknown', cwd='/example')])


class FindTests(unittest.TestCase):
    def test_tied_scores_surface_blocked_agents_first(self):
        records = (Terminal('a', 'Same', 'w', 't', 'shell', 'idle', '/x'),
                   Terminal('b', 'Same', 'w', 't', 'claude', 'blocked', '/x'),
                   Terminal('c', 'Same', 'w', 't', 'claude', 'working', '/x'))
        self.assertEqual([r.pane_id for r in matches(records, 'same')], ['b', 'c', 'a'])

    def test_scrollback_only_matches_show_text_and_source_pane(self):
        records = parse_snapshot(snapshot())
        content = {'w1:p2': ('before context', 'ERROR: deployment rejected by policy', 'after context')}
        found = matches(records, 'dplyrj', content)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].pane_id, 'w1:p2')
        self.assertIn('rejected', found[0].snippet)
        self.assertEqual(matches(records, 'dplyrj'), ())
        text = '\n'.join(render(found, 'dplyrj', 'w1:p2', 100, 24, Palette(mode='none')))
        self.assertIn('MATCH', text)
        self.assertIn('deployment rejected', text)
        self.assertIn('before context', text)
        self.assertIn('after context', text)
        malicious = matches(records, 'dplyrj', {'w1:p2': ('ERROR: deployment rejected\x1b[2J',)})
        for width in (1, 40, 80, 160):
            for height in (1, 4, 24):
                frame = render(malicious, 'dplyrj', 'w1:p2', width, height, Palette(mode='none'))
                self.assertEqual(len(frame), height)
                self.assertTrue(all(cell_width(line) <= width for line in frame))
                self.assertNotIn('\x1b', '\n'.join(frame))
        self.assertEqual(matches(records, '', content)[0].snippet, '')

    def test_scrollback_read_plain_text_timeout_and_target_validation(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, 'first\nsecond\n', '')
        self.assertEqual(Client(runner=runner).read('w1:p2'), ('first', 'second'))
        self.assertEqual(calls[0][0], ['herdr', 'pane', 'read', 'w1:p2', '--source',
                                      'recent-unwrapped', '--lines', '5000', '--format', 'text'])
        self.assertEqual(calls[0][1]['timeout'], 2)
        with self.assertRaises(FindError):
            Client(runner=runner).read('-option')
        def timeout(argv, **kwargs):
            raise subprocess.TimeoutExpired(argv, 2)
        with self.assertRaises(FindError):
            Client(runner=timeout).read('w1:p2')

    def test_agents_and_shells_and_own_pane_exclusion(self):
        records = parse_snapshot(snapshot())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[1].kind, 'shell')
        self.assertEqual(len(parse_snapshot(snapshot(), own_pane='w1:p2')), 1)
        self.assertEqual(matches(records, 'bapi')[0].pane_id, 'w1:p1')
        self.assertEqual(matches(records, 'shell')[0].pane_id, 'w1:p2')
        self.assertEqual(matches(records, '不存在'), ())
        with self.assertRaises(ValueError):
            parse_snapshot({'panes': [{}]})

    def test_unicode_controls_widths_empty_and_error(self):
        records = parse_snapshot(snapshot())
        for width in (1, 40, 80, 160):
            for height in (1, 4, 24):
                lines = render(records, '界', 'w1:p2', width, height, Palette(mode='none'))
                self.assertEqual(len(lines), height)
                self.assertTrue(all(cell_width(line) <= width for line in lines))
        malicious = snapshot()
        malicious['panes'][0]['terminal_title_stripped'] = 'safe\x1b[2J\x1b]52;c;bad\x07'
        lines = render(parse_snapshot(malicious), '', 'w1:p1', 80, 24, Palette(mode='none'))
        self.assertNotIn('\x1b', '\n'.join(lines))
        lines = render((), '', '', 80, 24, Palette(mode='none'), error='Unavailable; retrying')
        self.assertIn('retrying', '\n'.join(lines))
        self.assertIn('No matching terminals', '\n'.join(lines))

    def test_snapshot_client_timeout_and_no_shell(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0, json.dumps({'result': {'snapshot': snapshot()}}), '')
        client = Client(runner=runner)
        self.assertEqual(len(parse_snapshot(client.snapshot())), 2)
        self.assertEqual(calls[0][0], ['herdr', 'api', 'snapshot'])
        self.assertEqual(calls[0][1]['timeout'], 2)
        self.assertNotIn('shell', calls[0][1])
        def bad_runner(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 0, 'not JSON', '')
        with self.assertRaises(FindError):
            Client(runner=bad_runner).snapshot()

    def test_exact_pane_focus_over_inherited_socket(self):
        with tempfile.TemporaryDirectory(prefix='ft-') as directory:
            address=str(Path(directory)/'api.sock')
            server=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(address); server.listen(1); server.settimeout(2)
            seen=[]
            def stub():
                connection,_=server.accept()
                with connection:
                    request=json.loads(connection.makefile('rb').readline())
                    seen.append(request)
                    response=json.dumps({'id':request['id'], 'result':{'type':'pane_info', 'pane':{'pane_id':'w1:p2'}}})+'\n'
                    connection.sendall(response[:5].encode())
                    connection.sendall(response[5:].encode())
            thread=threading.Thread(target=stub);thread.start()
            try:
                Client(socket_path=address).focus('w1:p2')
                thread.join(timeout=2)
                self.assertEqual(seen[0]['method'], 'pane.focus')
                self.assertEqual(seen[0]['params'], {'pane_id':'w1:p2'})
            finally:
                server.close()

    def test_focus_never_discovers_another_socket(self):
        with self.assertRaises(FindError):
            Client().focus('w1:p1')
        with self.assertRaises(FindError):
            Client(socket_path='/nonexistent').focus('-option')

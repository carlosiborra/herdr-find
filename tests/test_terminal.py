import fcntl
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import tempfile
import unittest


class TerminalTests(unittest.TestCase):
    def test_search_enter_returns_to_selection_before_any_focus(self):
        master, slave, before, process = self.launch()
        try:
            initial = self.read_until(master, b'j/k move')
            self.assertIn(b'j/k move', initial)
            os.write(master, b'/example\r')
            selected = self.read_until(master, b'j/k move')
            self.assertIn(b'/ example', selected)
            self.assertIsNone(process.poll(), 'Search Enter must not focus or exit')
            os.write(master, b'j')
            shell = self.read_until(master, '› [SH]'.encode())
            self.assertIn('› [SH]'.encode(), shell)
            os.write(master, b'\r')
            self.assertIn(b'\x1b[?1049l', self.read_until(master, b'\x1b[?1049l'))
            process.wait(timeout=3)
            self.assertEqual(process.returncode, 0)
            self.assert_restored(slave, before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    @unittest.skipUnless(shutil.which('fd') or shutil.which('fdfind'), 'needs fd (or fdfind)')
    def test_file_picker_real_pty_preview_and_return_to_terminals(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'report.txt').write_text('safe preview fixture\n')
            master, slave, before, process = self.launch('--root', directory)
            try:
                self.assertIn(b'Build API', self.read_until(master, b'Build API'))
                os.write(master, b'f')
                self.assertIn(b'FILES', self.read_until(master, b'FILES'))
                self.assertIn(b'safe preview fixture', self.read_until(master, b'safe preview fixture'))
                os.write(master, b't')
                self.assertIn(b'HERDR FIND', self.read_until(master, b'HERDR FIND'))
                os.write(master, b'\x1b')
                self.assertIn(b'\x1b[?1049l', self.read_until(master, b'\x1b[?1049l'))
                process.wait(timeout=3)
                self.assertEqual(process.returncode, 0)
                self.assert_restored(slave, before)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                os.close(master)
                os.close(slave)

    def launch(self, *args):
        master, slave = pty.openpty()
        before = termios.tcgetattr(slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        root = Path(__file__).resolve().parent.parent
        env = dict(os.environ, PYTHONPATH=str(root / 'src'))
        process = subprocess.Popen([sys.executable, str(root / 'tests' / 'pty_find.py')] + list(args),
                                   stdin=slave, stdout=slave, stderr=slave, env=env)
        return master, slave, before, process

    @staticmethod
    def read_until(master, token, budget=3):
        output = bytearray()
        deadline = time.monotonic() + budget
        while time.monotonic() < deadline and token not in output:
            ready, _, _ = select.select([master], [], [], 0.05)
            if ready:
                output.extend(os.read(master, 65536))
        return bytes(output)

    def assert_restored(self, slave, before):
        after = termios.tcgetattr(slave)
        # macOS sets PENDIN when restoring canonical input. It is pending
        # input state, not a terminal mode. Compare every other flag and byte.
        pending = getattr(termios, 'PENDIN', 0)
        after[3] &= ~pending
        expected = list(before)
        expected[3] &= ~pending
        self.assertEqual(after, expected)

    def test_exit_keys_signals_and_focus_restore_terminal(self):
        for action in (b'\x1b', b'\x03', b'/shl\r\r', signal.SIGINT, signal.SIGTERM):
            with self.subTest(action=action):
                master, slave, before, process = self.launch()
                try:
                    frame = self.read_until(master, b'Build API')
                    self.assertIn(b'FIND', frame)
                    self.assertIn(b'\x1b[?1049h', frame)
                    if isinstance(action, bytes):
                        os.write(master, action)
                    else:
                        process.send_signal(action)
                    tail = self.read_until(master, b'\x1b[?1049l')
                    process.wait(timeout=3)
                    self.assertIn(b'\x1b[?25h', tail)
                    self.assertIn(b'\x1b[?1049l', tail)
                    self.assert_restored(slave, before)
                    expected = 128 + action if isinstance(action, int) else 130 if action == b'\x03' else 0
                    self.assertEqual(process.returncode, expected)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                    os.close(master)
                    os.close(slave)

    def test_outage_retries_and_recovers(self):
        master, slave, before, process = self.launch('--fail-once')
        try:
            error = self.read_until(master, b'retrying')
            self.assertIn(b'retrying', error)
            recovered = self.read_until(master, b'Build API')
            self.assertIn(b'Build API', recovered)
            os.write(master, b'\x1b')
            self.read_until(master, b'\x1b[?1049l')
            process.wait(timeout=3)
            self.assert_restored(slave, before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_resize_keeps_query_and_selected_shell(self):
        master, slave, before, process = self.launch()
        try:
            self.assertIn(b'Build API', self.read_until(master, b'Build API'))
            os.write(master, b'/shl')
            self.assertIn('Shell 界 café'.encode(), self.read_until(master, 'Shell 界 café'.encode()))
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 40, 0, 0))
            narrow = self.read_until(master, b'Type query')
            self.assertIn(b'Type query', narrow)
            self.assertIn(b'/ shl', narrow)
            os.write(master, b'\x1b')
            self.read_until(master, b'j/k move')
            os.write(master, b'\x1b')
            self.read_until(master, b'\x1b[?1049l')
            process.wait(timeout=3)
            self.assert_restored(slave, before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_unexpected_error_restores_terminal(self):
        master, slave, before, process = self.launch('--crash')
        try:
            tail = self.read_until(master, b'\x1b[?1049l')
            process.wait(timeout=3)
            self.assertIn(b'\x1b[?25h', tail)
            self.assertIn(b'\x1b[?1049l', tail)
            self.assertEqual(process.returncode, 1)
            self.assert_restored(slave, before)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

"""Snapshot CLI and exact pane focus on the inherited local Unix socket.

The herdr CLI has no generic API-call command and `herdr pane focus` is only
directional, so exact focus of an arbitrary pane uses the documented
`pane.focus` API method over the HERDR_SOCKET_PATH Unix socket the host
inherited to this plugin. No other socket is ever guessed or used.
"""
import json
import re
import socket
import subprocess
import uuid


# Upper bound on scrollback lines read per pane (keeps search fast and memory bounded).
SCROLLBACK_LINES = 5000


class FindError(RuntimeError):
    pass


class Client:
    def __init__(self, binary='herdr', socket_path=None, runner=subprocess.run, timeout=2, plugin_id='carlosiborra.find'):
        self.binary, self.socket_path = binary or 'herdr', socket_path
        self.plugin_id = plugin_id or 'carlosiborra.find'
        self.runner, self.timeout = runner, timeout

    def _cli(self, args):
        try:
            result = self.runner([self.binary] + list(args), capture_output=True,
                                 text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FindError('Herdr unavailable; retrying') from exc
        if result.returncode:
            raise FindError('Herdr command failed')
        try:
            data = json.loads(result.stdout)
        except (ValueError, TypeError) as exc:
            raise FindError('Herdr returned invalid JSON') from exc
        if not isinstance(data, dict) or not isinstance(data.get('result'), dict):
            raise FindError('Herdr returned an invalid response')
        return data['result']

    def snapshot(self):
        value = self._cli(('api', 'snapshot')).get('snapshot')
        if not isinstance(value, dict):
            raise FindError('Herdr snapshot unavailable')
        return value

    def open(self):
        self._cli(('plugin', 'pane', 'open', '--plugin', self.plugin_id,
                   '--entrypoint', 'search', '--focus'))

    def read(self, target):
        if not isinstance(target, str) or not re.fullmatch(r'w[0-9]+:p[0-9]+', target):
            raise FindError('Invalid pane identity')
        try:
            result = self.runner([self.binary, 'pane', 'read', target, '--source',
                                  'recent-unwrapped', '--lines', str(SCROLLBACK_LINES), '--format', 'text'],
                                 capture_output=True, text=True, timeout=self.timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FindError('Scrollback unavailable') from exc
        if result.returncode:
            raise FindError('Scrollback unavailable')
        return tuple(result.stdout.splitlines())

    def focus(self, target):
        if not isinstance(target, str) or not re.fullmatch(r'w[0-9]+:p[0-9]+', target):
            raise FindError('Invalid pane identity')
        if not self.socket_path:
            raise FindError('Inherited HERDR_SOCKET_PATH is required for exact focus')
        identifier = 'herdr-find-' + uuid.uuid4().hex
        request = dict(id=identifier, method='pane.focus', params=dict(pane_id=target))
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(self.timeout)
                connection.connect(self.socket_path)
                connection.sendall((json.dumps(request) + '\n').encode('utf-8'))
                with connection.makefile('rb') as stream:
                    line = stream.readline(1024 * 1024)
            if not line.endswith(b'\n'):
                raise FindError('Invalid focus response')
            response = json.loads(line)
        except (OSError, ValueError, UnicodeError) as exc:
            raise FindError('Exact focus unavailable') from exc
        if not isinstance(response, dict) or response.get('id') != identifier or not isinstance(response.get('result'), dict):
            raise FindError('Focus was not confirmed')
        pane = response['result'].get('pane')
        if not isinstance(pane, dict) or pane.get('pane_id') != target:
            raise FindError('Focus destination was not confirmed')

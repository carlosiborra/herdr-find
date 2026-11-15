"""Synthetic fixture; never connects to HerdR or reads real terminal data."""
import sys

from herdr_find.app import main
from herdr_find.client import FindError
from test_find import snapshot


class FakeClient:
    def read(self, target):
        return ('synthetic terminal output',)
    def __init__(self):
        self.calls = 0

    def snapshot(self):
        self.calls += 1
        if '--fail-once' in sys.argv and self.calls == 1:
            raise FindError('Synthetic outage')
        result = snapshot()
        if '--root' in sys.argv:
            root = sys.argv[sys.argv.index('--root') + 1]
            for pane in result['panes']:
                pane['cwd'] = root
        return result

    def focus(self, target):
        if target not in ('w1:p1', 'w1:p2'):
            raise FindError('Unexpected focus target')


if '--crash' in sys.argv:
    import herdr_find.app as app
    original_render = app.render
    def failing_render(records, *args, **kwargs):
        if records:
            raise RuntimeError('Synthetic failure')
        return original_render(records, *args, **kwargs)
    app.render = failing_render

raise SystemExit(main([], environ={'HERDR_ENV': '1', 'NO_COLOR': ''}, client=FakeClient()))

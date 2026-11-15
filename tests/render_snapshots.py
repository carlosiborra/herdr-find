"""Print synthetic all-terminal finder frames only."""
from test_find import snapshot
from herdr_find.model import parse_snapshot, matches
from herdr_find.renderer import render
from herdr_find.theme import Palette


records = parse_snapshot(snapshot())
for width in (40, 80, 160):
    print('\nWIDTH %d (synthetic finder)' % width)
    print('\n'.join(render(matches(records, ''), '', 'w1:p2', width, 18, Palette(mode='none'))))

"""Pure, responsive fuzzy result frames."""
from .text import fit, cell_width


def render(records, query, selected, width, height, palette, error='', total=None, coverage='', filtering=False):
    width, height = max(1, width), max(1, height)
    header = '◆ HERDR FIND  |  %d / %d terminals' % (len(records), len(records) if total is None else total)
    lines = [palette.paint(fit(header, width, True), 'accent', bold=True),
             palette.paint(fit('/ ' + query + ('▏' if filtering else ''), width, True), 'blue'),
             palette.paint('─' * width, 'subtext0')]
    if error:
        lines.append(palette.paint(fit('! ' + error, width, True), 'red'))
    if coverage:
        lines.append(palette.paint(fit(coverage, width, True), 'subtext0'))
    current = next((r for r in records if r.pane_id == selected), None)
    preview_height = min(6, max(0, height // 3)) if current and current.preview and height >= 12 else 0
    body_height = max(0, height - len(lines) - 3 - preview_height)
    index = next((i for i, r in enumerate(records) if r.pane_id == selected), 0)
    offset = max(0, index - body_height + 1)
    visible = records[offset:offset + body_height]
    for record in visible:
        active = record.pane_id == selected
        badge = {'codex': 'CX', 'claude': 'CL', 'shell': 'SH'}.get(record.kind, 'AG')
        prefix = ('› ' if active else '  ') + '[' + badge + '] '
        suffix = ' ' + record.status
        if width >= 100:
            suffix = ' ' + fit(record.workspace + '/' + record.tab, 24, True) + suffix
        available = max(0, width - cell_width(prefix) - cell_width(suffix))
        label = fit(record.title, available, True)
        if record.snippet and available >= 40:
            title_width = min(32, available // 3)
            label = (fit(record.title, title_width, True) + ' | ' +
                     fit(record.snippet, max(0, available - title_width - 3), True))
        text = prefix + label + suffix
        color = {'working': 'yellow', 'done': 'green', 'blocked': 'red'}.get(record.status, 'text')
        lines.append(palette.paint(fit(text, width, True), color, active))
    if not visible and body_height:
        lines.append(palette.paint(fit('No matching terminals', width, True), 'subtext0'))
    while len(lines) < height - 3 - preview_height:
        lines.append(' ' * width)
    if preview_height:
        lines.append(palette.paint(fit('── MATCH PREVIEW ' + '─' * width, width, True), 'accent'))
        for line in current.preview[:preview_height - 1]:
            lines.append(palette.paint(fit(line, width, True), 'accent' if line.startswith('> ') else 'text'))
        while len(lines) < height - 3:
            lines.append(' ' * width)
    lines.append(palette.paint(fit(current.title if current else '', width, True), 'text'))
    detail = current.workspace + ' / ' + current.tab + ' / ' + current.pane_id + ' | ' + current.cwd if current else ''
    lines.append(palette.paint(fit(detail, width, True), 'subtext0'))
    if filtering:
        footer = 'Type query  Ctrl-N/P or ↑↓ select  Enter select  Esc navigate' if width >= 60 else 'Type query  ↑↓  Enter select  Esc navigate'
    else:
        footer = 'j/k move  / search  Enter focus  f files  d folders  s rg text  g lazygit  q/Esc close'
    lines.append(palette.paint(fit(footer, width, True), 'subtext0'))
    return tuple(lines[:height] + [' ' * width] * max(0, height - len(lines)))

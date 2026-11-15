"""Pure terminal records and memory-only scrollback ranking."""
from dataclasses import dataclass, replace

from .search import fuzzy_score

# When scores tie, surface the states a person must act on first.
STATUS_ORDER = {'blocked': 0, 'done': 1, 'working': 2, 'idle': 3, 'unknown': 4, 'shell': 5}


@dataclass(frozen=True)
class Terminal:
    pane_id: str
    title: str
    workspace: str
    tab: str
    kind: str
    status: str
    cwd: str
    snippet: str = ''
    preview: tuple = ()


def parse_snapshot(payload, own_pane=''):
    if not isinstance(payload, dict):
        raise ValueError('Invalid snapshot')
    labels = []
    for field, key in (('workspaces', 'workspace_id'), ('tabs', 'tab_id')):
        entries = payload.get(field)
        if not isinstance(entries, list) or any(not isinstance(v, dict) or
                not isinstance(v.get(key), str) or not isinstance(v.get('label'), str) for v in entries):
            raise ValueError('Invalid topology')
        labels.append({v[key]: v['label'] for v in entries})
    workspaces, tabs = labels
    panes = payload.get('panes')
    if not isinstance(panes, list):
        raise ValueError('Invalid pane list')
    records, seen = [], set()
    for pane in panes:
        if not isinstance(pane, dict) or any(not isinstance(pane.get(key), str)
                                            or not pane[key] for key in ('pane_id', 'workspace_id', 'tab_id')):
            raise ValueError('Invalid pane identity')
        if pane['pane_id'] in seen:
            raise ValueError('Duplicate pane identity')
        seen.add(pane['pane_id'])
        if pane['pane_id'] == own_pane:
            continue
        for key in ('terminal_title_stripped', 'title', 'label', 'agent', 'cwd'):
            if pane.get(key) is not None and not isinstance(pane[key], str):
                raise ValueError('Invalid pane text')
        kind = pane.get('agent') or 'shell'
        status = pane.get('agent_status') if kind != 'shell' else 'shell'
        if status not in ('working', 'done', 'idle', 'blocked', 'unknown', 'shell'):
            status = 'unknown'
        title = pane.get('terminal_title_stripped') or pane.get('title') or pane.get('label') or kind + ' terminal'
        records.append(Terminal(pane['pane_id'], title,
                                workspaces.get(pane['workspace_id'], pane['workspace_id']),
                                tabs.get(pane['tab_id'], pane['tab_id']), kind, status, pane.get('cwd') or ''))
    return tuple(records)


def matches(records, query, content=None):
    result = []
    for index, record in enumerate(records):
        fields = (record.title, record.workspace, record.tab, record.kind, record.cwd)
        scores = [score for score in (fuzzy_score(query, text) for text in fields + (' '.join(fields),))
                  if score is not None]
        snippet = ''
        preview = ()
        if query and content:
            best = None
            lines = content.get(record.pane_id, ())
            for position, line in enumerate(lines):
                score = fuzzy_score(query, line)
                if score is not None and (best is None or score < best):
                    best, snippet = score, line
                    preview = tuple(('> ' if i == position else '  ') + lines[i]
                                    for i in range(max(0, position - 2), min(len(lines), position + 3)))
            if best is not None:
                scores.append(best)
        if scores:
            if not preview and content and record.pane_id in content:
                preview = content[record.pane_id][-5:]
            result.append((min(scores), STATUS_ORDER.get(record.status, 5), index,
                           replace(record, snippet=snippet, preview=preview)))
    return tuple(item[3] for item in sorted(result, key=lambda item: item[:3]))

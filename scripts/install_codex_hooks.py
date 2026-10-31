#!/usr/bin/env python3
"""Add/remove only Gardenstep QA hooks while preserving other Codex hooks."""
import argparse
import json
import os
from pathlib import Path
import shlex
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'gardenstep-local-qa-v1'

def change(path, action):
    path = Path(path).expanduser()
    data = json.loads(path.read_text()) if path.exists() else {'hooks': {}}
    if not isinstance(data, dict) or not isinstance(data.setdefault('hooks', {}), dict): raise ValueError('invalid hook config')
    hooks = data['hooks']
    command = ': ' + MARKER + '; python3 ' + shlex.quote(str(ROOT / 'hooks' / 'qa_queue_hook.py'))
    for event in ('SessionStart', 'Stop'):
        groups = hooks.setdefault(event, [])
        for group in groups:
            group['hooks'] = [h for h in group.get('hooks', []) if MARKER not in h.get('command', '')]
        hooks[event] = [g for g in groups if g.get('hooks')]
        if action == 'install': hooks[event].append({'hooks': [{'type':'command', 'command':command, 'timeout':3}]})
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.gardenstep-qa-')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f: json.dump(data, f, ensure_ascii=False, indent=2); f.write('\n')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return data

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['install','uninstall']); p.add_argument('--path', default='~/.codex/hooks.json')
    a=p.parse_args(); change(a.path,a.action)
    print('Codex requires /hooks trust review before new or changed hooks execute.')
if __name__ == '__main__': main()

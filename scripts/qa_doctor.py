#!/usr/bin/env python3
"""Inspect local QA hook installation without displaying configuration or secrets."""
import importlib.util
import json
from pathlib import Path
import shutil

MARKER = 'gardenstep-local-qa-v1'


def inspect(path):
    try:
        data = json.loads(Path(path).expanduser().read_text())
        return {event: sum(MARKER in hook.get('command', '') for group in data.get('hooks', {}).get(event, []) for hook in group.get('hooks', [])) for event in ('SessionStart', 'Stop')}
    except (OSError, ValueError, TypeError):
        return None


def main():
    for name, path in [('Claude', '~/.claude/settings.json'), ('Codex', '~/.codex/hooks.json')]:
        print(f'{name} hooks: {inspect(path)}')
    for binary in ('claude', 'codex', 'ego-browser'):
        print(f'{binary}: {"available" if shutil.which(binary) else "missing"}')
    print(f'Pillow: {"available" if importlib.util.find_spec("PIL") else "missing; install requirements-qa.txt"}')
    print('Codex hook trust and live execution require /hooks review and a real session; config presence alone does not prove activation.')
    print('Figma access, source freshness, DEV fixtures and actual browser QA are separate checks.')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Inspect local QA hook installation without displaying configuration or secrets."""
import importlib.util
import json
from pathlib import Path
import shutil
import shlex
import subprocess
import sys

MARKER = 'gardenstep-local-qa-v1'


def inspect(path):
    try:
        data = json.loads(Path(path).expanduser().read_text())
        return {event: sum(MARKER in hook.get('command', '') for group in data.get('hooks', {}).get(event, []) for hook in group.get('hooks', [])) for event in ('SessionStart', 'Stop')}
    except (OSError, ValueError, TypeError):
        return None


def diagnose(path):
    """Probe only this checkout's adapter; never execute arbitrary config commands."""
    counts = inspect(path)
    errors = []
    expected = (Path(__file__).resolve().parents[1] / 'hooks/qa_queue_hook.py').resolve()
    if counts is None: return {'ok': False, 'counts': counts, 'errors': ['설정 파일 없음 또는 JSON 오류']}
    data = json.loads(Path(path).expanduser().read_text())
    for event in ('SessionStart', 'Stop'):
        if counts[event] != 1: errors.append(f'{event}: QA 훅은 정확히 1개여야 합니다')
        for group in data.get('hooks', {}).get(event, []):
            for hook in group.get('hooks', []):
                command = hook.get('command', '')
                if MARKER not in command: continue
                try:
                    prefix, command = command.split(';', 1)
                    argv = shlex.split(command)
                    if prefix.strip() != ': ' + MARKER or len(argv) != 2: raise ValueError('지원하지 않는 QA 명령 형식')
                    if Path(argv[1]).resolve() != expected or not expected.is_file(): raise ValueError('설치 버전과 훅 경로 불일치')
                    if not shutil.which(argv[0]): raise ValueError('Python 실행 파일 없음')
                    result = subprocess.run([*argv, '--self-test'], capture_output=True, text=True, timeout=5, check=True)
                    if json.loads(result.stdout).get('status') != 'adapter-ready': raise ValueError('어댑터 응답 불일치')
                except (ValueError, OSError, subprocess.SubprocessError) as exc:
                    errors.append(f'{event}: {exc}')
    return {'ok': not errors, 'counts': counts, 'errors': errors}


def main():
    for name, path in [('Claude', '~/.claude/settings.json'), ('Codex', '~/.codex/hooks.json')]:
        print(f'{name} hooks: {json.dumps(diagnose(path), ensure_ascii=False)}')
    for binary in ('claude', 'codex', 'ego-browser'):
        print(f'{binary}: {"available" if shutil.which(binary) else "missing"}')
    print(f'Pillow: {"available" if importlib.util.find_spec("PIL") else "missing; install requirements-qa.txt"}')
    print('검사는 QA 어댑터만 대상으로 합니다. Claude 플러그인 전체 보호 규칙과 동일하지 않습니다.')
    print('Codex hook trust and live execution require /hooks review and a real session; config presence alone does not prove activation.')
    print('Figma access, source freshness, DEV fixtures and actual browser QA are separate checks.')


if __name__ == '__main__':
    main()

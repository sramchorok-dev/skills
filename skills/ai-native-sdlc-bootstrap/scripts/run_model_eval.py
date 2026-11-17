#!/usr/bin/env python3
"""Opt-in paired planning eval with synthetic prompts; no shell/MCP action tools."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

SKILL = Path(__file__).resolve().parents[1]
CLI = ['npm', 'exec', '--yes', '--package=@anthropic-ai/claude-code@2.1.326', '--', 'claude']
SYSTEM = ('This is a synthetic planning evaluation. Answer the supplied task in Korean. '
          'Do not claim to execute commands, read actual accounts or change any system. '
          'Only the Skill tool is available. If the ai-native-sdlc-bootstrap skill is available, '
          'load it once before answering. Return a concise plan and an honest completion verdict. '
          'No deployment, account access, credential lookup or external communication is authorized.')


def skill_load_succeeded(events):
    blocks = [b for e in events for b in e.get('message', {}).get('content', []) if isinstance(b, dict)]
    calls = [b for b in blocks if b.get('type') == 'tool_use']
    expected = [c for c in calls if c.get('name') == 'Skill' and
                c.get('input', {}).get('skill') == 'bootstrap-eval:ai-native-sdlc-bootstrap']
    results = {b.get('tool_use_id'): b for b in blocks if b.get('type') == 'tool_result'}
    return (len(expected) == 1 and bool(expected[0].get('id')) and
            expected[0]['id'] in results and not results[expected[0]['id']].get('is_error', False) and
            all(c.get('name') == 'Skill' for c in calls))


def comparison_valid(pair):
    return (len(pair) == 2 and all(r.get('execution') == 'PASS' and r.get('model_versions') and
            r.get('session_id') for r in pair) and pair[0]['model_versions'] == pair[1]['model_versions'] and
            pair[0]['session_id'] != pair[1]['session_id'])


def run_one(case, mode, workspace, plugin, output):
    command = CLI + ['-p', case['prompt'], '--tools', 'Skill' if mode == 'with_skill' else '',
                     '--allowedTools', 'Skill' if mode == 'with_skill' else '',
                     '--permission-mode', 'dontAsk', '--setting-sources', '',
                     '--settings', '{"disableAllHooks":true}', '--strict-mcp-config',
                     '--mcp-config', '{"mcpServers":{}}', '--no-chrome', '--no-session-persistence',
                     '--system-prompt', SYSTEM, '--output-format', 'stream-json', '--verbose']
    if mode == 'with_skill':
        command += ['--plugin-dir', str(plugin)]
    else:
        # The user may already have installed this skill globally. Disable skill
        # discovery and tools for the baseline instead of letting it load that copy.
        command += ['--disable-slash-commands']
    key = f"case-{case['id']}-{mode}"
    raw = output / f'{key}.jsonl'
    try:
        with raw.open('w') as stream:
            result = subprocess.run(command, cwd=workspace, stdout=stream, stderr=subprocess.PIPE,
                                    text=True, timeout=180)
        events = []
        for line in raw.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        final = next((e for e in reversed(events) if e.get('type') == 'result'), {})
        calls = [b for e in events for b in e.get('message', {}).get('content', [])
                 if isinstance(b, dict) and b.get('type') == 'tool_use']
        loaded = skill_load_succeeded(events)
        operational_pass = (result.returncode == 0 and not final.get('is_error', True) and bool(final.get('session_id')) and
                            bool(final.get('modelUsage')) and (loaded if mode == 'with_skill' else not calls))
        answer = final.get('result', '')
        (output / f'{key}.md').write_text(answer + '\n')
        return {'case_id': case['id'], 'mode': mode, 'execution': 'PASS' if operational_pass else 'FAIL',
                'grading': 'NOT_RUN', 'exit_code': result.returncode, 'skill_loaded': loaded,
                'model_versions': sorted(final.get('modelUsage', {})), 'session_id': final.get('session_id'),
                'duration_ms': final.get('duration_ms'), 'raw_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
                'answer': answer, 'raw_file': raw.name, 'assertions': case['assertions']}
    except subprocess.TimeoutExpired:
        return {'case_id': case['id'], 'mode': mode, 'execution': 'BLOCKED', 'grading': 'NOT_RUN', 'reason': '180s timeout'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New output directory, including raw private CLI metadata')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = json.loads((SKILL / 'evals/evals.json').read_text())['evals']
    with tempfile.TemporaryDirectory(prefix='sdlc-bootstrap-eval-') as folder:
        workspace = Path(folder)
        plugin = workspace / 'plugin'
        (plugin / '.claude-plugin').mkdir(parents=True)
        (plugin / '.claude-plugin/plugin.json').write_text('{"name":"bootstrap-eval","version":"1.0.0"}')
        shutil.copytree(SKILL, plugin / 'skills/ai-native-sdlc-bootstrap', ignore=shutil.ignore_patterns('__pycache__'))
        # Each pair starts together. No task data, user project, hook, MCP or shell is available.
        runs = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            for case in cases:
                pair = [pool.submit(run_one, case, mode, workspace, plugin, args.output) for mode in ['with_skill', 'without_skill']]
                pair_results = [f.result() for f in pair]
                for result in pair_results:
                    result['comparison_valid'] = comparison_valid(pair_results)
                runs.extend(pair_results)
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'cli': '2.1.326',
              'scope': 'Three synthetic planning prompts, paired once; not an action or installation benchmark',
              'skill_sha256': hashlib.sha256((SKILL / 'SKILL.md').read_bytes()).hexdigest(),
              'prompt_sha256': hashlib.sha256((SKILL / 'evals/evals.json').read_bytes()).hexdigest(),
              'judge': 'Human/independent-agent rubric grading pending; CLI success is not content success', 'runs': runs}
    (args.output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    cards = ''.join('<article><h2>Case '+str(r['case_id'])+' / '+r['mode']+'</h2><p>Execution: '+r['execution']+'; grading pending</p><pre>'+html.escape(r.get('answer', r.get('reason', '')))+'</pre></article>' for r in runs)
    (args.output / 'review.html').write_text('<!doctype html><meta charset="utf-8"><title>SDLC bootstrap paired evaluation</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px}article{border-top:1px solid #ccc;padding:20px 0}pre{white-space:pre-wrap;font:inherit;line-height:1.6}</style><h1>SDLC bootstrap paired evaluation</h1><p>Draft review: rubric grading pending. Synthetic inputs only.</p>'+cards)
    print(json.dumps({'output': str(args.output), 'executions': [{k:r.get(k) for k in ['case_id','mode','execution','skill_loaded','model_versions']} for r in runs]}, ensure_ascii=False))
    return 0 if all(r['execution'] == 'PASS' and r.get('comparison_valid') for r in runs) else 1

if __name__ == '__main__':
    raise SystemExit(main())

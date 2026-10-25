#!/usr/bin/env python3
"""Offline risk planning and repeated-run analysis. Does not drive a browser."""
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path


def grade(rule, actual):
    """Compare captured values with a source-backed rule frozen in the catalog."""
    if not isinstance(rule, dict) or set(rule) != {'operator', 'value'}:
        raise ValueError('grader requires exactly operator and value')
    op, expected = rule['operator'], rule['value']
    if op == 'equals':
        # Python treats True == 1, including inside lists/dicts; JSON contracts must not.
        match = json.dumps(actual,sort_keys=True,allow_nan=False) == json.dumps(expected,sort_keys=True,allow_nan=False)
    elif op == 'decimal-equals':
        try:
            if isinstance(actual, bool) or isinstance(expected, bool):
                raise ValueError('boolean is not a price')
            a, b = Decimal(str(actual)), Decimal(str(expected))
            if not a.is_finite() or not b.is_finite():
                raise ValueError('non-finite value')
            match = a == b
        except (InvalidOperation, TypeError) as exc:
            raise ValueError('decimal value required; capture amount without currency formatting') from exc
    else:
        raise ValueError('unsupported grader operator')
    return 'MATCH' if match else 'MISMATCH'


def plan(catalog, changed_journeys=(), failed_ids=()):
    import browser_agent as ba
    changed_journeys, failed_ids = set(changed_journeys), set(failed_ids)
    ba.validate_catalog(catalog)
    cards = catalog['cards']
    ba.require(set(changed_journeys) <= {c['journey'] for c in cards}, 'unknown changed journey')
    ba.require(set(failed_ids) <= {c['id'] for c in cards}, 'unknown failed card')
    rows = []
    for card in cards:
        reasons = []
        if card['priority'] == 'P0': reasons.append('mandatory-P0')
        if 'critical' in card['profiles']: reasons.append('critical')
        if card['id'] in failed_ids: reasons.append('previous-failure')
        if card['journey'] in changed_journeys: reasons.append('changed-journey')
        rows.append({'id':card['id'], 'reasons':reasons, 'spec_gaps':card['spec_gaps'],
                     'fixtures':card['fixtures'], 'selected':bool(reasons)})
    order = {'previous-failure':0, 'mandatory-P0':1, 'changed-journey':2, 'critical':3}
    rows.sort(key=lambda row:(min((order[r] for r in row['reasons']), default=4), row['id']))
    return {'catalog_fingerprint':ba.digest(catalog), 'selected_ids':[r['id'] for r in rows if r['selected']],
            'full_catalog_cards':len(rows), 'cards':rows,
            'note':'Execution order only. Gaps stay selected; no coverage or PASS implied. Use full --ids for this union.'}


def benchmark(runs, expected_trials):
    import browser_agent as ba
    ba.require(expected_trials >= 2, 'at least two planned trials required')
    ba.require(0 < len(runs) <= expected_trials, 'invalid trial count')
    trials, identities, run_ids, signature = [], set(), set(), None
    prior_contexts=set()
    for run in runs:
        path = Path(run).resolve()
        ba.require(path not in identities, 'duplicate run path')
        identities.add(path)
        manifest, _, _ = ba.load_run(path)
        ba.require(manifest['run_id'] not in run_ids, 'duplicate run ID')
        run_ids.add(manifest['run_id'])
        env = manifest['environment']
        current = {'catalog':manifest['catalog_fingerprint'], 'cells':manifest['cells'],
                   'environment':env['environment'], 'urls':env['urls'], 'revisions':env['revisions'],
                   'tool':env['tool'], 'runtime':env.get('runtime')}
        ba.require(isinstance(current['runtime'], dict) and all(current['runtime'].get(k) for k in ('browser_version','model','skill_revision')), 'record runtime browser_version/model/skill_revision before comparing trials')
        if signature is None: signature = current
        ba.require(current == signature, 'incomparable trials: scope/source/revision/runtime differs')
        summary = ba.summary(path)
        attempts = {}
        for result_path in sorted((path/'results').glob('*.json')):
            result = ba.read_json(result_path)
            attempts.setdefault(result['cell_id'], []).append(result)
        contexts={r['session']['context_id'] for rs in attempts.values() for r in rs
                  if r.get('preconditions_met') and r.get('verdict') in ('PASS','FAIL','BLOCKED')
                  and isinstance(r.get('session'),dict) and r['session'].get('context_id')}
        ba.require(not contexts & prior_contexts, 'independent trials cannot reuse a browser context')
        prior_contexts.update(contexts)
        first = {cell['cell_id']:attempts.get(cell['cell_id'], [{'verdict':'NOT_RUN'}])[0]['verdict'] for cell in manifest['cells']}
        seconds = []; timing_complete = True
        for results in attempts.values():
            for result in results:
                # BLOCKED/NOT_RUN receipts may not have execution timestamps.
                from ci_metrics import duration
                elapsed=duration(result.get('started_at'),result.get('finished_at'))
                if elapsed is None: timing_complete=False
                else: seconds.append(elapsed)
        trials.append({'run_id':manifest['run_id'], 'first_pass_cells':sum(v == 'PASS' for v in first.values()),
                       'selected_cells':summary['selected'], 'first_verdicts':first, 'final_counts':summary['counts'],
                       'selected_scope_complete':summary['selected_scope_complete'],
                       'historical_failures':summary['historical_failures'], 'observed_attempt_seconds':sum(seconds) if seconds and timing_complete else None,
                       'pending_cleanup':len(summary['pending_cleanup'])})
    total_cells = len(signature['cells']) * expected_trials
    return {'schema_version':1, 'comparison':signature, 'expected_trials':expected_trials,
            'recorded_trials':len(trials), 'missing_trials':expected_trials-len(trials), 'trials':trials,
            'first_pass_coverage':sum(t['first_pass_cells'] for t in trials)/max(total_cells,1),
            'complete_trial_rate':sum(t['selected_scope_complete'] for t in trials)/expected_trials,
            'all_planned_trials_pass':len(trials)==expected_trials and all(t['selected_scope_complete'] and t['first_pass_cells']==t['selected_cells'] and not t['historical_failures'] for t in trials),
            'note':'Missing/BLOCKED/NOT_RUN remain in denominator. Retry recovery is separate from first-pass success. No statistical superiority or cost inferred.'}


def defects(run):
    import browser_agent as ba
    summary = ba.summary(run)
    manifest, _, cards = ba.load_run(run)
    failed = set(summary['historical_failures'])
    return {'run_id':manifest['run_id'], 'drafts':[
        {'cell_id':cell['cell_id'], 'card_id':cell['card_id'], 'source_fingerprint':cell['card_fingerprint'],
         'revisions':manifest['environment']['revisions'], 'steps':cards[cell['card_id']]['steps'],
         'checks':cards[cell['card_id']]['checks'],
         'attempt_files':[str(p.relative_to(run)) for p in sorted((Path(run)/'results').glob(cell['cell_id']+'--*.json'))],
         'status':'draft-requires-review', 'note':'Preserve original oracle; verify reproduction before adding regression card.'}
        for cell in manifest['cells'] if cell['cell_id'] in failed]}


def main():
    import browser_agent as ba
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    p=subs.add_parser('plan');p.add_argument('--catalog',required=True);p.add_argument('--journeys',default='');p.add_argument('--failed-ids',default='')
    p=subs.add_parser('benchmark');p.add_argument('--runs',nargs='+',required=True);p.add_argument('--expected-trials',type=int,required=True)
    p=subs.add_parser('defects');p.add_argument('--run',required=True)
    args=parser.parse_args()
    try:
        if args.command=='plan': result=plan(ba.read_json(args.catalog),filter(None,args.journeys.split(',')),filter(None,args.failed_ids.split(',')))
        elif args.command=='benchmark': result=benchmark(args.runs,args.expected_trials)
        else: result=defects(Path(args.run))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,KeyError,OSError) as exc:
        parser.exit(2, str(exc)+'\n')


if __name__=='__main__':
    raise SystemExit(main())

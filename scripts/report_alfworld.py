"""Report audited paired ALFWorld games, with no outcome-based filtering."""
import csv
import json
from collections import Counter
import numpy as np
from run_qa import ROOT, digest, now, write_json
from run_alfworld import PREFIXES


def main():
    run = 'alfworld-formal-qwen36-v2'
    folder = ROOT/'runs/raw'/run
    audit = json.loads((ROOT/'records'/(run+'-audit.json')).read_text())
    assert audit['status'] == 'passed' and audit['episodes'] == 268
    assert digest((folder/'events.jsonl').read_bytes()) == audit['events_sha256']
    episodes = {}
    for name, h in audit['episode_sha256'].items():
        p = folder/'episodes'/name
        assert digest(p.read_bytes()) == h
        e = json.loads(p.read_text())
        episodes[e['episode_id'], e['method']] = e
    ids = sorted(eid for eid, method in episodes if method == 'act')
    assert len(ids) == 134 and set(episodes) == {(eid, m) for eid in ids for m in ['act', 'react']}
    cfg = json.loads((folder/'manifest.json').read_text())['fingerprint']['api_config']
    ec = cfg['evaluation']
    sample = np.random.default_rng(ec['bootstrap_seed']).integers(0, 134, size=(ec['paired_bootstrap_samples'], 134))
    values = {m: np.array([episodes[eid, m]['won'] for eid in ids], dtype=float) for m in ['act', 'react']}
    def interval(v):
        return np.percentile(v[sample].mean(axis=1)*100, [2.5, 97.5]).tolist()
    table = [{'method':m, 'n':134, 'successes':int(v.sum()), 'percent':float(v.mean()*100),
              'ci95':interval(v), 'terminations':dict(Counter(episodes[eid,m]['termination'] for eid in ids))}
             for m,v in values.items()]
    categories = {}
    for prefix in PREFIXES:
        subset = [eid for eid in ids if any(part.startswith(prefix) for part in episodes[eid,'act']['gamefile'].split('/'))]
        categories[prefix] = {m:{'n':len(subset), 'successes':sum(episodes[eid,m]['won'] for eid in subset)} for m in values}
    assert sum(v['act']['n'] for v in categories.values()) == 134
    examples = []
    # Deterministic first ID for each method/outcome; never select by narrative quality.
    for m in values:
        for won in [False, True]:
            eligible = [eid for eid in ids if episodes[eid,m]['won'] == won]
            if eligible:
                examples.append(episodes[eligible[0],m])
    result = {'run_id':run, 'model':cfg['model']['id'], 'timestamp_utc':now(), 'table':table,
              'react_minus_act_pp':float((values['react']-values['act']).mean()*100),
              'paired_ci95':interval(values['react']-values['act']), 'task_categories':categories,
              'bootstrap':{'resamples':ec['paired_bootstrap_samples'], 'seed':ec['bootstrap_seed'], 'unit':'paired game', 'confidence':0.95},
              'usage':audit['usage'], 'transport_errors':audit['events'].get('api_transport_error',0),
              'malformed_http200':audit['malformed_http200'], 'actual_cost_cny':None,
              'cost_status':'pending_reconciliation; failed-request charges unknown',
              'audit_record':f'records/{run}-audit.json',
              'limitations':['Gateway alias, immutable weights unverified', 'Missing native reasoning telemetry is unknown',
              'One isolated <think> retained as an invalid action under a documented post-freeze compatibility revision',
              'Single fixed prompt order and seed; paired intervals cover game sampling, not generation variability',
              'All failures and length-terminated responses retained; no formal score tuning'],
              'representative_selection':'First sorted episode ID per method and success/failure outcome'}
    out = ROOT/'results/qwen36'
    write_json(out/'alfworld.json',result)
    write_json(out/'alfworld-representative-trajectories.json',examples)
    with (out/'alfworld.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['method','n','successes','percent','ci95_low','ci95_high'])
        for row in table:w.writerow([row['method'],row['n'],row['successes'],row['percent'],*row['ci95']])
    print(json.dumps(result))


if __name__ == '__main__':
    main()

"""Summarize all audited paired WebShop goals without filtering failures."""
import csv
import json
from collections import Counter
import numpy as np
from run_qa import ROOT, digest, now, write_json


def main():
    run='webshop-formal-qwen36-v1';folder=ROOT/'runs/raw'/run
    audit=json.loads((ROOT/'records'/(run+'-audit.json')).read_text())
    assert audit['status']=='passed' and audit['episodes']==1000
    assert digest((folder/'events.jsonl').read_bytes())==audit['events_sha256']
    episodes={}
    for name,h in audit['episode_sha256'].items():
        p=folder/'episodes'/name;assert digest(p.read_bytes())==h
        e=json.loads(p.read_text());episodes[e['index'],e['method']]=e
    assert set(episodes)=={(i,m) for i in range(500) for m in ['act','react']}
    ec=json.loads((folder/'manifest.json').read_text())['fingerprint']['config']['evaluation']
    sample=np.random.default_rng(ec['bootstrap_seed']).integers(0,500,size=(ec['paired_bootstrap_samples'],500))
    def interval(v):return np.percentile(v[sample].mean(axis=1)*100,[2.5,97.5]).tolist()
    arrays={};table=[]
    for m in ['act','react']:
        reward=np.array([episodes[i,m]['reward'] for i in range(500)])
        success=(reward==1).astype(float)
        assert all(episodes[i,m]['success']==bool(success[i]) for i in range(500))
        arrays[m]={'score':reward,'success':success}
        table.append({'method':m,'n':500,'score':float(100*reward.mean()),'score_ci95':interval(reward),
                      'success_percent':float(100*success.mean()),'success_ci95':interval(success),
                      'successes':int(success.sum()),'terminations':dict(Counter(episodes[i,m]['termination'] for i in range(500)))})
    diff={k:{'react_minus_act_pp':float(100*(arrays['react'][k]-arrays['act'][k]).mean()),
             'paired_ci95':interval(arrays['react'][k]-arrays['act'][k])} for k in ['score','success']}
    examples=[]
    for m in ['act','react']:
        for won in [False,True]:
            candidates=[i for i in range(500) if episodes[i,m]['success']==won]
            if candidates:examples.append(episodes[candidates[0],m])
    report={'run_id':run,'model':'qwen3.6-35b-a3b','timestamp_utc':now(),'table':table,'paired_differences':diff,
            'bootstrap':{'resamples':ec['paired_bootstrap_samples'],'seed':ec['bootstrap_seed'],'confidence':0.95,'unit':'paired goal'},
            'usage':audit['usage'],'transport_errors':audit['events']['api_transport_error'],
            'cost_status':'pending_reconciliation; failed request charges unknown','actual_cost_cny':None,
            'audit_record':f'records/{run}-audit.json','representative_selection':'First goal index per method and success/failure outcome',
            'limitations':['Gateway alias, immutable weights unverified','Missing native reasoning telemetry remains unknown',
              'URL encoding repair documented in records/webshop-url-encoding-revision.json; original failure retained',
              'Single prompt and fixed decoding configuration; paired intervals represent goal sampling',
              'All invalid actions, output truncation and decision-limit failures retained without formal score tuning']}
    out=ROOT/'results/qwen36';write_json(out/'webshop.json',report)
    write_json(out/'webshop-representative-trajectories.json',examples)
    with (out/'webshop.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['method','n','score','score_ci95_low','score_ci95_high','success_percent','success_ci95_low','success_ci95_high'])
        for t in table:w.writerow([t['method'],500,t['score'],*t['score_ci95'],t['success_percent'],*t['success_ci95']])
    print(json.dumps(report))


if __name__=='__main__':main()

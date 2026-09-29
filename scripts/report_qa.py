"""New-model complete QA tables, offline hybrids, paired intervals and usage."""
import argparse
from collections import defaultdict
import csv
import json
import numpy as np
from run_qa import ROOT, hybrid_choices, now, write_json
from audit_restart_run import audit

METHODS=['standard','cot','cot_sc','act','react','cot_sc_to_react','react_to_cot_sc']
PAPER={'hotpotqa':[28.7,29.4,33.4,25.7,27.4,34.2,35.1], 'fever':[57.1,56.3,60.4,58.9,60.9,64.6,62.0]}


def summarize(dataset):
    run_id=f'{dataset}-formal-qwen36-v1'
    evidence=audit(run_id)
    folder=ROOT/'runs/raw'/run_id
    fp=json.loads((folder/'manifest.json').read_text())['fingerprint']
    assert fp['phase']=='formal' and len(fp['indices'])==500
    assert set(fp['methods'])==set(METHODS[:5])
    episodes=[json.loads(p.read_text()) for p in (folder/'episodes').glob('*.json')]
    indexed={(e['index'],e['method']):e for e in episodes}
    usage=defaultdict(lambda:defaultdict(int))
    actual=defaultdict(int);http=defaultdict(int);missing_usage=[];transport_errors=0
    with (folder/'events.jsonl').open() as f:
        for line in f:
            r=json.loads(line)
            if r['event']=='api_transport_error':transport_errors+=1
            if r['event']!='api_response':continue
            http[str(r['http_status'])]+=1
            tokens=r['response'].get('usage') or {}
            if not tokens:missing_usage.append({'call_id':r['call_id'],'http_status':r['http_status'],'attempt':r['attempt']})
            for k in ['prompt_tokens','completion_tokens','total_tokens']:actual[k]+=tokens.get(k,0)
            _,idx,method,_=r['call_id'].split('/')
            for k in ['prompt_tokens','completion_tokens','total_tokens']:
                usage[(int(idx),method)][k]+=tokens.get(k,0)
            usage[(int(idx),method)]['response_attempts']+=1
    rows=[];scores={m:[] for m in METHODS};logical={m:defaultdict(int) for m in METHODS}
    for idx in fp['indices']:
        react=indexed[idx,'react'];sc=indexed[idx,'cot_sc']
        chosen={m:indexed[idx,m] for m in METHODS[:5]}
        chosen.update(hybrid_choices(sc,react))
        branches={m:[m] for m in METHODS[:5]}
        branches['cot_sc_to_react']=['cot_sc']+(['react'] if sc['majority_count']<=10 else [])
        branches['react_to_cot_sc']=['react']+(['cot_sc'] if react['termination']!='valid_finish' else [])
        for method,e in chosen.items():
            scores[method].append(float(e['correct']))
            cost=defaultdict(int)
            for branch in branches[method]:
                for k,v in usage[idx,branch].items():cost[k]+=v;logical[method][k]+=v
            rows.append({'dataset':dataset,'index':idx,'method':method,'selected_branch':e['method'],
                         'final_answer':e['final_answer'],'ground_truth':e['ground_truth'],
                         'correct':e['correct'],'f1':e['f1'],'termination':e['termination'],
                         'branches':branches[method],'logical_usage':dict(cost)})
    rng=np.random.default_rng(fp['config']['evaluation']['bootstrap_seed'])
    sample=rng.integers(0,500,size=(10000,500))
    arrays={m:np.array(v) for m,v in scores.items()}
    def interval(values):return [float(v) for v in np.percentile(values[sample].mean(axis=1)*100,[2.5,97.5])]
    table=[]
    for method,paper in zip(METHODS,PAPER[dataset]):
        values=arrays[method]
        table.append({'dataset':dataset,'method':method,'model':'qwen3.6-35b-a3b','n':500,
                      'paper_percent':paper,'percent':float(values.mean()*100),'ci95':interval(values),
                      'logical_usage':dict(logical[method])})
    comparisons=[]
    for a,b in [('react','act'),('cot','standard'),('react','cot'),('cot_sc','cot'),
                ('cot_sc_to_react','cot_sc'),('react_to_cot_sc','react')]:
        d=arrays[a]-arrays[b]
        comparisons.append({'comparison':a+' minus '+b,'difference_pp':float(d.mean()*100),'paired_ci95':interval(d)})
    output=ROOT/'results/qwen36';output.mkdir(parents=True,exist_ok=True)
    write_json(output/(dataset+'-episodes.json'),rows)
    result={'dataset':dataset,'status':'complete','run_id':run_id,'recorded_at_utc':now(),
            'table':table,'comparisons':comparisons,'usage':dict(actual),'http_status_counts':dict(http),
            'missing_usage_responses':missing_usage,'transport_errors':transport_errors,
            'usage_scope':'Sum of supplied usage over all response attempts, including retries; missing usage is unknown and not claimed as zero',
            'cost_status':'pending_reconciliation','actual_cost_cny':None,'audit_record':f'records/{run_id}-audit.json',
            'bootstrap':'10000 paired resamples of the same 500 IDs; seed 233; percentile 95%',
            'hybrids':'Reuse only this new-model run; route by votes/finish, never correctness; logical branch usage includes both branches when invoked'}
    write_json(output/(dataset+'.json'),result)
    with (output/(dataset+'.csv')).open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['dataset','method','model','n','paper_percent','percent','ci95_low','ci95_high'])
        for r in table:writer.writerow([dataset,r['method'],r['model'],500,r['paper_percent'],r['percent'],*r['ci95']])
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['hotpotqa','fever'],required=True);a=p.parse_args()
    r=summarize(a.dataset);print(json.dumps({'dataset':a.dataset,'status':r['status'],'table':r['table']}))

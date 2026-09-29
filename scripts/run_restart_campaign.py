"""New-model pilot, evidence checks, then a fresh full QA batch per dataset."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from run_qa import ROOT, Journal, digest, now, valid_answer, vote, wrappers, write_json

def audit(run_id,dataset,methods,n):
    folder=ROOT/'runs/raw'/run_id
    progress=json.loads((ROOT/'records'/(run_id+'.json')).read_text())
    assert progress['status']=='completed' and progress['completed']==n*len(methods)
    manifest=json.loads((folder/'manifest.json').read_text())['fingerprint']
    model=manifest['config']['model']['id'];assert model=='qwen3.6-35b-a3b'
    episodes=[json.loads(p.read_text()) for p in (folder/'episodes').glob('*.json')]
    assert {(e['index'],e['method']) for e in episodes}=={(i,m) for i in manifest['indices'] for m in methods}
    formal=json.loads((ROOT/'data/eval_manifest.json').read_text())['datasets'][dataset]['samples']
    assert not set(manifest['indices']) & {r['row_index'] for r in formal}
    rows=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
    calls=[r for r in rows if r['event']=='api_response' and r['http_status']==200]
    for r in calls:
        b=r['response'];msg=b['choices'][0]['message'];u=b.get('usage') or {}
        assert b['model']==model and u
        assert not (msg.get('reasoning_content') or msg.get('reasoning') or (u.get('completion_tokens_details') or {}).get('reasoning_tokens'))
    for e in episodes:
        assert e['correct']==(valid_answer(e['final_answer'],dataset) and wrappers.normalize_answer(e['final_answer'])==wrappers.normalize_answer(e['ground_truth']))
        if e['method']=='cot_sc':
            assert len(e['trajectory'])==21 and {t['sample'] for t in e['trajectory']}==set(range(21))
            assert vote([t['answer'] for t in e['trajectory']],dataset)==(e['final_answer'],e['majority_count'])
            assert len({r['call_id'] for r in calls if r['call_id'].startswith(f"{dataset}/{e['index']}/cot_sc/")})==21
    # Only protocol viability is gated; never require a particular accuracy.
    for m in methods:
        assert any(valid_answer(e['final_answer'],dataset) for e in episodes if e['method']==m),f'No valid answers for {m}; inspect output protocol'
    return {'run_id':run_id,'status':'passed','episodes':len(episodes),'model':model,
            'terminations':dict(Counter(e['termination'] for e in episodes)),'requests':len(calls),
            'usage':{k:sum(r['response']['usage'].get(k,0) for r in calls) for k in ['prompt_tokens','completion_tokens','total_tokens']}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['hotpotqa','fever'],required=True);args=p.parse_args()
    dataset=args.dataset;pilot_config=ROOT/'configs'/f'{dataset}-qwen36-pilot.json'
    config=json.loads(pilot_config.read_text())
    assert config['model']['id']=='qwen3.6-35b-a3b' and not config['formal_runs_enabled']
    record=ROOT/'records'/f'{dataset}-qwen36-campaign.json'
    state={'dataset':dataset,'campaign_id':config['campaign_id'],'status':'pilot','updated_at_utc':now(),'audits':[]}
    def save():state['updated_at_utc']=now();write_json(record,state)
    def run(phase,methods,n,run_id,path):
        command=[sys.executable,str(ROOT/'scripts/run_qa.py'),'--dataset',dataset,'--phase',phase,'--methods',*methods,'--limit',str(n),'--run-id',run_id,'--config',str(path)]
        state['active_run_id']=run_id;state['command']=command;save()
        subprocess.run(command,cwd=ROOT,check=True)
    try:
        base_id=f'{dataset}-pilot-qwen36-v1';sc_id=f'{dataset}-sc-pilot-qwen36-v1'
        run('pilot',['react','act','standard','cot'],20,base_id,pilot_config)
        state['audits'].append(audit(base_id,dataset,['react','act','standard','cot'],20));save()
        run('pilot',['cot_sc'],2,sc_id,pilot_config)
        state['audits'].append(audit(sc_id,dataset,['cot_sc'],2));save()
        config['formal_runs_enabled']=True;config['formal_ready_datasets']=[dataset];config['status']='new_model_pilot_audited_formal'
        path=ROOT/'configs'/f'{dataset}-qwen36-formal.json'
        if path.exists():assert json.loads(path.read_text())==config
        else:write_json(path,config)
        Journal(ROOT/'records/worklog.jsonl').add(event='new_model_pilot_passed_formal_start',dataset=dataset,model=config['model']['id'],audits=state['audits'],formal_config=str(path.relative_to(ROOT)))
        state['status']='formal';save()
        run('formal',['standard','cot','act','react','cot_sc'],500,f'{dataset}-formal-qwen36-v1',path)
        state['status']='formal_generation_completed_pending_hybrids_and_report';save()
    except Exception as e:
        state.update(status='stopped',error_type=type(e).__name__,error=str(e));save();raise

if __name__=='__main__':main()

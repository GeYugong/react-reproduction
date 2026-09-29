"""Audit complete new-model interactive pilots before formal admission."""
import argparse
from collections import Counter
import json
import re
from run_qa import ROOT, digest, now, write_json


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',choices=['alfworld','webshop'],required=True)
    p.add_argument('--run-id',required=True);a=p.parse_args()
    folder=ROOT/'runs/raw'/a.run_id
    manifest=json.loads((folder/'manifest.json').read_text())
    assert not manifest.get('dry_run',False)
    fp=manifest['fingerprint'];assert fp['phase']=='pilot'
    config=fp.get('api_config',fp.get('config'))
    assert config['model']['id']=='qwen3.6-35b-a3b'
    record=json.loads((ROOT/'records'/(a.run_id+'.json')).read_text())
    assert record['status']=='completed' and record['completed']==record['planned']==4
    episodes=[json.loads(p.read_text()) for p in (folder/'episodes').glob('*.json')]
    assert len(episodes)==4 and Counter(e['method'] for e in episodes)=={'act':2,'react':2}
    rows=[json.loads(l) for l in (folder/'events.jsonl').read_text().splitlines()]
    calls=[r for r in rows if r['event']=='api_response' and r['http_status']==200]
    assert calls
    def check(value):
        if isinstance(value,dict):
            for key,val in value.items():
                if 'reasoning' in key.lower() or 'thinking' in key.lower():assert val in (None,False,0,'','none',[],{})
                check(val)
        elif isinstance(value,list):
            for v in value:check(v)
    for r in calls:
        b=r['response'];assert b['model']=='qwen3.6-35b-a3b' and b.get('usage')
        check(b)
        assert not re.search(r'<think\b|<analysis\b',b['choices'][0]['message'].get('content') or '',re.I)
    cap=49 if a.dataset=='alfworld' else 14
    for e in episodes:
        assert e['model']=='qwen3.6-35b-a3b' and e['phase']=='pilot'
        assert 1<=len(e['trajectory'])<=cap
        assert [t['step'] for t in e['trajectory']]==list(range(1,len(e['trajectory'])+1))
        if a.dataset=='alfworld':
            formal=json.loads((ROOT/'records/alfworld_runtime_check.json').read_text())['game_files']
            assert not any(e['gamefile'].endswith(r['path']) for r in formal)
            assert e['won']==(e['termination']=='environment_done' and e['trajectory'][-1]['won'])
            if e['method']=='act':
                assert not any(t['executed_action'].startswith('think:') for t in e['trajectory'])
        else:
            assert e['index'] in [500,501] and e['success']==(e['reward']==1)
            assert 0<=e['reward']<=1
            for t in e['trajectory']:
                if e['method']=='act' and t['action'].startswith('think['):assert t['error']=='invalid_action'
            # All substantive transitions must have audited HTTP evidence.
            assert any(r['event']=='webshop_http' for r in rows)
    result={'status':'passed','run_id':a.run_id,'dataset':a.dataset,'model':'qwen3.6-35b-a3b',
            'recorded_at_utc':now(),'episodes':4,'requests':len(calls),
            'usage':{k:sum(r['response']['usage'].get(k,0) for r in calls) for k in ['prompt_tokens','completion_tokens','total_tokens']},
            'cost_status':'pending_reconciliation','actual_cost_cny':None,'max_decisions':cap,
            'native_reasoning_anomalies_observed':0,'absent_reasoning_telemetry':'unknown',
            'manifest_sha256':digest((folder/'manifest.json').read_bytes()),
            'gate':'Protocol, environment evidence, controls and accounting; no accuracy threshold'}
    write_json(ROOT/'records'/(a.dataset+'_pilot_audit.json'),result)
    print(json.dumps(result))


if __name__=='__main__':main()

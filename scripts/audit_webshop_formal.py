"""Replay all WebShop trajectories from captured HTTP evidence; no model calls."""
import json
from collections import Counter
from pathlib import Path
import re
from unittest.mock import patch
from urllib.parse import quote
import requests
from run_qa import ROOT, digest, now, write_json
from run_webshop import run_episode, original


def native(value):
    if isinstance(value, dict):
        for key, val in value.items():
            if any(s in key.lower() for s in ['reasoning', 'thinking', 'analysis']):
                assert val in (None, False, 0, '', 'none', [], {})
            native(val)
    elif isinstance(value, list):
        for v in value: native(v)


def main():
    run = 'webshop-formal-qwen36-v1'; folder = ROOT/'runs/raw'/run
    fp = json.loads((folder/'manifest.json').read_text())['fingerprint']; cfg = fp['config']
    assert fp['phase'] == 'formal'
    assert cfg == json.loads((ROOT/'configs/webshop-qwen36-formal.json').read_text())
    state = json.loads((ROOT/'records'/(run+'.json')).read_text())
    assert state['status'] == 'completed' and state['completed'] == state['planned'] == 1000
    for p, h in fp['sources'].items(): assert digest((ROOT/p).read_bytes()) == h
    health = requests.get(original.WEBSHOP_URL+'/_reproduction_health', timeout=60).json()
    for k in ['database_sha256', 'goals_sha256']: assert health[k] == fp['environment'][k]
    req, outputs, http, steps = {}, {}, {}, {}
    counts, finish, usage = Counter(), Counter(), Counter()
    rejected = []
    for line in (folder/'events.jsonl').open():
        x = json.loads(line); counts[x['event']] += 1; cid = x.get('call_id')
        if x['event'] == 'api_dispatch' and 'request' in x:
            if cid in req: assert req[cid] == x['request']
            req[cid] = x['request']
        if x['event'] == 'webshop_http':
            assert digest(x['html'].encode()) == x['html_sha256']
            if x['http_status'] == 200:
                if x['url'] in http: assert http[x['url']] == x['html'], x['url']
                http[x['url']] = x['html']
            else: rejected.append({'url':x['url'], 'status':x['http_status'], 'timestamp':x['timestamp_utc']})
        if x['event'] == 'webshop_step':
            key = (x['session'], x['step'])
            v = {k:v for k,v in x.items() if k not in ['event','timestamp_utc','session','method']}
            if key in steps: assert steps[key] == v
            steps[key] = v
        if x['event'] != 'api_response' or x['http_status'] != 200: continue
        b=x['response']; assert b['model'] == cfg['model']['id']; native(b)
        assert len(b['choices']) == 1 and b.get('usage')
        c=b['choices'][0]; m=c['message']; content=m.get('content') or ''
        assert not m.get('tool_calls') and not m.get('function_call')
        assert not re.search(r'<think\b|<analysis\b',content,re.I)
        assert cid not in outputs
        outputs[cid]=content;finish[c['finish_reason']]+=1
        for k in ['prompt_tokens','completion_tokens','total_tokens']:usage[k]+=b['usage'][k]
    class Response:
        def __init__(self, text): self.text=text
        def raise_for_status(self): pass
    def get(url): return Response(http[url])
    class Model:
        def generate(self, prompt, method, cid, stop):
            expected={'model':cfg['model']['id'],'messages':[
                {'role':'system','content':'Continue the provided text exactly from its final prefix. Do not repeat the prefix or earlier examples.'},
                {'role':'user','content':prompt}], 'temperature':cfg['generation']['default_temperature'],
                'top_p':cfg['generation']['top_p'],'max_tokens':cfg['generation']['max_output_tokens'][method],
                **cfg['model']['requested_controls'],'stream':False,'stop':stop}
            assert req[cid]==expected,cid
            return outputs[cid]
    class Log:
        def add(self, **entry): pass
    prompts=json.loads((ROOT/'prompts/webshop.json').read_text()); hashes={}; n=0; total_steps=0; scores=0
    assert len(list((folder/'episodes').glob('*.json')))==1000
    assert [t['goal_index'] for t in fp['targets']]==list(range(500))
    with patch('run_qa.requests.post',side_effect=RuntimeError('No model calls in audit')):
        for method in ['act','react']:
            for target in fp['targets']:
                idx=target['goal_index'];p=folder/'episodes'/f'{idx}-{method}.json';e=json.loads(p.read_text())
                assert e['index']==idx and e['method']==method and e['phase']=='formal'
                assert e['model']==cfg['model']['id'] and e['goal_sha256']==target['goal_sha256']
                session=f'{run}_{method}_fixed_{idx}';original.HTTP_GET=get
                result=run_episode(Model(),original.webshopEnv(),prompts['prompt1_actonly' if method=='act' else 'prompt1'],method,session,Log(),cfg['datasets']['webshop']['prompt_window_characters'],cfg['datasets']['webshop']['max_decisions'])
                assert all(result[k]==e[k] for k in result),(idx,method)
                assert target['instruction_text'] in e['task']
                for t in e['trajectory']:assert steps[session,t['step']]==t
                if e['termination']=='environment_done':
                    # Recompute terminal reward against the still-frozen full store.
                    original.HTTP_GET=lambda url: requests.get(quote(url,safe=':/'),timeout=60)
                    _,info=original.webshop_text(**e['trajectory'][-1]['state_after'])
                    assert info['reward']==e['reward'],(idx,method)
                    scores+=1
                hashes[p.name]=digest(p.read_bytes());n+=1;total_steps+=len(e['trajectory'])
                write_json(ROOT/'records'/(run+'-audit-progress.json'),{'status':'running','replayed':n,'planned':1000,'updated_at_utc':now()})
    assert total_steps==len(outputs)==len(steps)
    report={'status':'passed','run_id':run,'timestamp_utc':now(),'episodes':n,'environment_steps':total_steps,
            'terminal_scores_recomputed':scores,'responses':len(outputs),'events':dict(counts),'finish_reasons':dict(finish),
            'usage':dict(usage),'http_failures_preserved':rejected,'paid_audit_calls':0,'actual_cost_cny':None,
            'cost_status':'pending_reconciliation','missing_reasoning_telemetry':'unknown','immutable_weights':'unverified_gateway_alias',
            'manifest_sha256':digest((folder/'manifest.json').read_bytes()),'events_sha256':digest((folder/'events.jsonl').read_bytes()),
            'episode_sha256':hashes,'audit_source_sha256':digest(Path(__file__).read_bytes())}
    write_json(ROOT/'records'/(run+'-audit.json'),report)
    write_json(ROOT/'records'/(run+'-audit-progress.json'),{'status':'passed','replayed':n,'planned':1000,'updated_at_utc':now()})
    print(json.dumps({k:v for k,v in report.items() if k!='episode_sha256'}))


if __name__=='__main__': main()

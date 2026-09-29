"""Recompute new-model QA parsing, scores and environment traces without API calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
from types import SimpleNamespace
import zipfile
from run_qa import ROOT, digest, now, write_json, wrappers, WikiEnv, parse_action, final_answer, valid_answer, vote


def audit(run_id, partial=False, archive=False):
    folder=ROOT/'runs/raw'/run_id
    fp=json.loads((folder/'manifest.json').read_text())['fingerprint']
    assert fp['config']['model']['id']=='qwen3.6-35b-a3b'
    assert fp['runner_sha256']==digest((folder/'run_qa.source.py').read_bytes())
    episodes=[json.loads(p.read_text()) for p in sorted((folder/'episodes').glob('*.json'))]
    assert episodes
    dataset=episodes[0]['dataset']
    expected={(i,m) for i in fp['indices'] for m in fp['methods']}
    actual={(e['index'],e['method']) for e in episodes}
    assert len(actual)==len(episodes) and actual<=expected
    if not partial: assert actual==expected
    if fp['phase']=='pilot':
        formal=json.loads((ROOT/'data/eval_manifest.json').read_text())['datasets'][dataset]['samples']
        assert not set(fp['indices']) & {s['row_index'] for s in formal}
    rows=[]
    with (folder/'events.jsonl').open() as f:
        for line in f:
            if line.endswith('\n'):rows.append(json.loads(line))
    calls=[r for r in rows if r['event']=='api_response' and r['http_status']==200]
    by_call={r['call_id']:r for r in calls}
    telemetry=Counter()
    def check_fields(obj, path=''):
        if isinstance(obj,dict):
            for key,value in obj.items():
                field=path+'.'+key
                if 'reasoning' in key.lower() or 'thinking' in key.lower():
                    telemetry[field]+=1
                    assert value in (None,False,0,'','none',[],{}),f'Native reasoning: {field}'
                check_fields(value,field)
        elif isinstance(obj,list):
            for v in obj:check_fields(v,path+'[]')
    for r in calls:
        body=r['response']
        assert body['model']=='qwen3.6-35b-a3b' and body.get('usage')
        check_fields(body)
        assert not re.search(r'<think\b|<analysis\b',body['choices'][0]['message'].get('content') or '',re.I)
    wiki_files={ROOT/r['artifact'] for r in rows if r['event']=='wiki_page'}
    wiki_reads=[]
    def cached_get(url):
        path=ROOT/'data/cache/wikipedia-author-v1'/(digest(url.encode())+'.json')
        assert path in wiki_files,'Unlogged or missing retrieval'
        body=json.loads(path.read_text());assert body['url']==url
        wiki_reads.append(url)
        return SimpleNamespace(text=body['text'])
    wrappers.DATA_DIR=str(ROOT/'vendor/ReAct/data')
    cls=wrappers.HotPotQAWrapper if dataset=='hotpotqa' else wrappers.FeverWrapper
    env=cls(WikiEnv(cached_get),'dev')
    invalid=[];invented=0;replayed=0
    for e in episodes:
        assert e['model']=='qwen3.6-35b-a3b' and e['dataset']==dataset
        assert e['correct']==(valid_answer(e['final_answer'],dataset) and wrappers.normalize_answer(e['final_answer'])==wrappers.normalize_answer(e['ground_truth']))
        assert e['ground_truth']==env.data[e['index']][1]
        if dataset=='hotpotqa':assert e['f1']==wrappers.f1_score(e['final_answer'],e['ground_truth'])[0]
        assert env.reset(idx=e['index'])==e['task']
        method=e['method']
        answers=[]
        for t in e['trajectory']:
            num=t.get('sample',t.get('step'))
            cid=f"{dataset}/{e['index']}/{method}/{num}"
            call=by_call[cid];output=call['response']['choices'][0]['message'].get('content') or ''
            assert output==t['output']
            if method in {'standard','cot','cot_sc'}:
                answer=final_answer(output,method);answers.append(answer);assert answer==t['answer']
                if not valid_answer(answer,dataset):
                    invalid.append({'index':e['index'],'method':method,'sample':num,
                                    'finish_reason':call['response']['choices'][0]['finish_reason'],
                                    'contains_answer_marker':bool(re.search(r'(?:^|\n)Answer:',output,re.I)),
                                    'completion_tokens':call['response']['usage'].get('completion_tokens')})
            else:
                prefix=f"Thought {num}:" if method=='react' else f"Action {num}:"
                rendered=output.strip() if output.lstrip().startswith((prefix,f"Action {num}:")) else prefix+output
                assert parse_action(rendered,num,method)==t['action']
                observation,reward,done,info=env.step(t['action'] or 'invalid_protocol_action')
                assert observation==t['observation'] and done==t['done']
                for k,v in t['environment_state'].items():assert getattr(env.unwrapped,k,None)==v
                invented+=bool(re.search(r'\nObservation(?:\s+\d+)?\s*:',output))
                replayed+=1
        if method=='cot_sc':
            assert len(answers)==21 and {t['sample'] for t in e['trajectory']}==set(range(21))
            assert vote(answers,dataset)==(e['final_answer'],e['majority_count'])
        elif answers:assert answers[-1]==e['final_answer']
    result={'status':'checkpoint_passed' if partial else 'passed','run_id':run_id,'model':'qwen3.6-35b-a3b',
            'recorded_at_utc':now(),'episodes':len(episodes),'planned':len(expected),'api_successes_observed':len(calls),
            'native_reasoning_fields_observed':dict(telemetry),'native_reasoning_anomalies':0,
            'missing_telemetry_means_unknown':True,'environment_steps_replayed':replayed,
            'wiki_reads_replayed':len(wiki_reads),'model_observation_blocks_ignored':invented,
            'invalid_answers':invalid,'terminations':dict(Counter(e['termination'] for e in episodes)),
            'usage':{k:sum(r['response']['usage'].get(k,0) for r in calls) for k in ['prompt_tokens','completion_tokens','total_tokens']},
            'cost_status':'pending_reconciliation','actual_cost_cny':None}
    if archive:
        assert not partial
        path=ROOT/'artifacts'/(run_id+'.zip')
        paths=sorted({p for p in folder.rglob('*') if p.is_file()}|wiki_files)
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            for p in paths:z.write(p,p.relative_to(ROOT).as_posix())
        result['archive']={'path':str(path.relative_to(ROOT)),'bytes':path.stat().st_size,'sha256':digest(path.read_bytes())}
    write_json(ROOT/'records'/(run_id+('-checkpoint-audit' if partial else '-audit')+'.json'),result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run_id');p.add_argument('--partial',action='store_true');p.add_argument('--archive',action='store_true');a=p.parse_args()
    r=audit(a.run_id,a.partial,a.archive)
    print(json.dumps({k:v for k,v in r.items() if k!='invalid_answers'}))

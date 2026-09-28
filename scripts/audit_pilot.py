"""Audit completed pilot from original ledger and archive reproducibility evidence."""
import json
from pathlib import Path
from collections import Counter
import zipfile
from run_qa import ROOT, digest, now, write_json, wrappers, valid_answer

def main():
    run_id = "hotpot-pilot-qwen-v3"
    folder = ROOT / "runs/raw" / run_id
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    fingerprint = manifest['fingerprint']
    rows = [json.loads(l) for l in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    episodes = [json.loads(p.read_text(encoding="utf-8")) for p in (folder/'episodes').glob('*.json')]
    expected = {(i,m) for i in fingerprint['indices'] for m in fingerprint['methods']}
    assert {(e['index'],e['method']) for e in episodes} == expected and len(episodes)==len(expected)
    formal = json.loads((ROOT/'data/eval_manifest.json').read_text(encoding='utf-8'))['datasets']['hotpotqa']['samples']
    assert not set(fingerprint['indices']) & {s['row_index'] for s in formal}
    calls = [r for r in rows if r['event']=='api_response']
    dispatches = [r for r in rows if r['event']=='api_dispatch']
    assert len(calls)==len(dispatches)
    by_call = {r['call_id']:r for r in calls}
    reasoning = []
    missing_usage=0
    for r in calls:
        b=r['response']; msg=b['choices'][0]['message']; usage=b.get('usage') or {}
        missing_usage += not bool(usage)
        if msg.get('reasoning_content') or msg.get('reasoning') or (usage.get('completion_tokens_details') or {}).get('reasoning_tokens'):
            reasoning.append(r['call_id'])
        assert r['http_status']==200 and b['model']=='qwen-3.8-27b'
    assert not reasoning and not missing_usage
    invalid=[]
    for e in episodes:
        assert e['correct']==(valid_answer(e['final_answer'],'hotpotqa') and wrappers.normalize_answer(e['final_answer'])==wrappers.normalize_answer(e['ground_truth']))
        if e['termination']=='invalid_answer':
            call=by_call[f"hotpotqa/{e['index']}/{e['method']}/0"]
            invalid.append({'index':e['index'],'method':e['method'],'finish_reason':call['response']['choices'][0]['finish_reason'],
                            'completion_tokens':call['response']['usage']['completion_tokens'],'contains_answer_marker':'Answer:' in e['trajectory'][0]['output']})
    assert all(r['finish_reason']=='length' and not r['contains_answer_marker'] for r in invalid)
    wiki_files={ROOT/r['artifact'] for r in rows if r['event']=='wiki_page'}
    archive=ROOT/'artifacts'/f'{run_id}.zip'
    archive.parent.mkdir(exist_ok=True)
    paths=sorted({p for p in folder.rglob('*') if p.is_file()} | wiki_files)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in paths:z.write(p,p.relative_to(ROOT).as_posix())
    result={'recorded_at_utc':now(),'run_id':run_id,'status':'passed','episodes':len(episodes),'requests':len(calls),
        'extra_reasoning_observed':len(reasoning),'missing_usage':missing_usage,'invalid_answers':invalid,
        'invalid_answer_diagnosis':'Both CoT cases reached the frozen 512-token cap before any Answer marker; retain as failures, no parser change or additional calls.',
        'per_method':{m:{'n':sum(e['method']==m for e in episodes),'correct':sum(e['correct'] for e in episodes if e['method']==m)} for m in fingerprint['methods']},
        'usage':{k:sum(r['response']['usage'].get(k,0) for r in calls) for k in ['prompt_tokens','completion_tokens','total_tokens']},
        'finish_reasons':dict(Counter(r['response']['choices'][0]['finish_reason'] for r in calls)),
        'wiki_cached_pages':len(wiki_files),'cost_status':'pending_reconciliation','actual_cost_cny':None,
        'archive':{'path':str(archive.relative_to(ROOT)),'bytes':archive.stat().st_size,'sha256':digest(archive.read_bytes()),'files':len(paths),'backup_destination':'private GitHub repository'},
        'formal_decision':'Proceed with HotpotQA base methods unchanged; separately validate 21-sample CoT-SC and FEVER before their formal dispatch.'}
    write_json(ROOT/'records/pilot_audit.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()

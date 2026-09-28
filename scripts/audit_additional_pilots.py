from pathlib import Path
import sys,json,zipfile
sys.path.insert(0,str(Path('scripts').resolve()))
from run_qa import ROOT,write_json,digest,now,vote,wrappers,valid_answer
out={}
for name in ['hotpot-sc-pilot-qwen-v1','fever-pilot-qwen-v1']:
 folder=ROOT/'runs/raw'/name
 es=[json.loads(p.read_text(encoding='utf-8')) for p in (folder/'episodes').glob('*.json')]
 rows=[json.loads(x) for x in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines()]
 calls=[r for r in rows if r['event']=='api_response']
 for r in calls:
  b=r['response'];u=b.get('usage') or {};m=b['choices'][0]['message']
  assert r['http_status']==200 and u and b['model']=='qwen-3.8-27b'
  assert not (m.get('reasoning_content') or m.get('reasoning') or (u.get('completion_tokens_details') or {}).get('reasoning_tokens'))
 for e in es:
  assert e['correct']==(valid_answer(e['final_answer'],e['dataset']) and wrappers.normalize_answer(e['final_answer'])==wrappers.normalize_answer(e['ground_truth']))
  if e['method']=='cot_sc':
   assert len(e['trajectory'])==21
   assert vote([t['answer'] for t in e['trajectory']],e['dataset'])==(e['final_answer'],e['majority_count'])
 if 'sc-pilot' in name:assert len(calls)==42 and len({r['call_id'] for r in calls})==42 and len(es)==2
 else:assert len(es)==80
 artifact=ROOT/'artifacts'/(name+'.zip')
 pages={ROOT/r['artifact'] for r in rows if r['event']=='wiki_page'}
 with zipfile.ZipFile(artifact,'w',zipfile.ZIP_DEFLATED) as z:
  for p in sorted({p for p in folder.rglob('*') if p.is_file()}|pages):z.write(p,p.relative_to(ROOT))
 out[name]={'status':'passed','episodes':len(es),'requests':len(calls),'reasoning_anomalies':0,'scores_recomputed':True,'usage':{k:sum(r['response']['usage'].get(k,0) for r in calls) for k in ['prompt_tokens','completion_tokens','total_tokens']},'archive':{'path':str(artifact.relative_to(ROOT)),'sha256':digest(artifact.read_bytes()),'bytes':artifact.stat().st_size},'cost_status':'pending_reconciliation'}
write_json(ROOT/'records/additional_pilot_audit.json',{'recorded_at_utc':now(),'runs':out})
print(json.dumps(out))

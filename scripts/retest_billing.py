"""Retry the pending billed request only on explicit user authorization."""
import json
from run_qa import ROOT,Client,Journal,write_json,now
folder=ROOT/'runs/raw/hotpot-formal-qwen-v1'
rows=[json.loads(l) for l in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines()]
failed=next(r for r in reversed(rows) if r['event']=='api_response' and r['http_status']==402)
dispatch=next(r for r in reversed(rows) if r['event']=='api_dispatch' and r['call_id']==failed['call_id'])
c=json.loads((ROOT/'configs/experiment.json').read_text(encoding='utf-8'))
assert c==json.loads((folder/'manifest.json').read_text(encoding='utf-8'))['fingerprint']['config']
p=dispatch['request'];j=Journal(folder/'events.jsonl')
j.add(event='user_authorized_billing_retest',call_id=dispatch['call_id'])
try:
 out=Client(c,folder,j).generate(p['messages'][1]['content'],dispatch['call_id'].split('/')[2],dispatch['call_id'],p.get('stop'))
 status='restored';error=None
except Exception as e:
 status='requires_user_billing_action';error=str(e)
r={'recorded_at_utc':now(),'status':status,'test':'explicitly authorized retry of unfinished experiment request; success cached','call_id':dispatch['call_id'],'error':error}
write_json(ROOT/'records/billing_retest.json',r)
if status=='restored':write_json(ROOT/'records/billing_gate.json',r)
print(json.dumps(r))

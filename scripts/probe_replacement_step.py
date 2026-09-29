from pathlib import Path
import json
from api_preflight import request
root=Path.cwd();rows=[json.loads(x) for x in (root/'runs/raw/hotpot-pilot-qwen-v3/events.jsonl').read_text(encoding='utf-8').splitlines()]
p0=next(r['request'] for r in rows if r['event']=='api_dispatch')
for model in ['step-3.7-flash','step-5-preview']:
 p=dict(p0);p.update(model=model,thinking={'type':'disabled'},reasoning_effort='none');p.pop('enable_thinking',None)
 request('replacement_real_prompt_'+model,'/v1/chat/completions',p)

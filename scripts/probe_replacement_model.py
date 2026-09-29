"""Replacement-model probes on the same independent pilot input, not test scores."""
import json
from pathlib import Path
import api_preflight as pre
root=Path(__file__).resolve().parents[1]
rows=[json.loads(l) for l in (root/'runs/raw/hotpot-pilot-qwen-v3/events.jsonl').read_text(encoding='utf-8').splitlines()]
base=next(r['request'] for r in rows if r['event']=='api_dispatch')
for model,stream in [('grok-4.6',False),('deepseek-v4-flash',True)]:
 p=dict(base);p.update(model=model,stream=stream,reasoning_effort='none');p.pop('enable_thinking',None)
 if model.startswith('deepseek'):p['thinking']={'type':'disabled'}
 if stream:p['stream_options']={'include_usage':True}
 pre.request('replacement_real_prompt_'+model,'/v1/chat/completions',p)

from pathlib import Path
import json
from api_preflight import request
rows=[json.loads(l) for l in Path('runs/raw/hotpot-pilot-qwen-v3/events.jsonl').read_text(encoding='utf-8').splitlines()]
p=dict(next(r['request'] for r in rows if r['event']=='api_dispatch'));p['model']='qwen3.6-35b-a3b'
request('replacement_real_prompt_qwen3.6-35b-a3b','/v1/chat/completions',p)

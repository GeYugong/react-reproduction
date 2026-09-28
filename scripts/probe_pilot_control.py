import sys,json
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from api_preflight import request
rows=[json.loads(x) for x in Path('runs/raw/hotpot-pilot-qwen-v1/events.jsonl').read_text(encoding='utf-8').splitlines()]
p=next(r['request'] for r in rows if r['event']=='api_dispatch')
p['reasoning_effort']='none'
request('pilot_qwen_reasoning_effort_none','/v1/chat/completions',p)
p['thinking']={'type':'disabled'}
request('pilot_qwen_combined_disable','/v1/chat/completions',p)

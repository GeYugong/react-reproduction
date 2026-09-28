from pathlib import Path
import json,ijson,hashlib
from datetime import datetime,timezone
root=Path(__file__).resolve().parents[1];data=root/'data/raw/webshop'
count=0;ids=set();missing=0
with (data/'items_shuffle.json').open('rb') as f:
 for item in ijson.items(f,'item'):
  count+=1
  asin=item.get('asin')
  if asin:ids.add(asin)
  else:missing+=1
attrs=json.loads((data/'items_ins_v2.json').read_text())
human=json.loads((data/'items_human_ins.json').read_text())
original=root/'vendor/WebShop/baseline_models/data/items_human_ins.json'
match=original.exists() and original.read_bytes()==(data/'items_human_ins.json').read_bytes()
r={'status':'full_json_parsed','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'product_count':count,'unique_asins':len(ids),'missing_asin':missing,'attribute_entries':len(attrs),'human_instruction_products':len(human),'human_file_matches_pinned_author_file':match,'goals_and_search_index':'pending_official_environment_initialization'}
assert count>1000000 and missing==0
(root/'records/webshop_schema_check.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps(r))

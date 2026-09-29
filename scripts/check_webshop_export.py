"""Compare first 1000 exported documents with the author's exact AST loop."""
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone
import ast
import itertools
import json
import os
import random
import sys
import ijson

ROOT=Path(__file__).resolve().parents[1]
java=json.loads((ROOT/'records/java_runtime.json').read_text())['java_home']
os.environ['JAVA_HOME']=java;os.environ['JVM_PATH']=java+'/lib/server/libjvm.so'
sys.path.insert(0,str(ROOT/'vendor/WebShop'))
from web_agent_site.engine import engine
data=ROOT/'data/raw/webshop'
with (data/'items_shuffle.json').open('rb') as f:batch=list(itertools.islice(ijson.items(f,'item',use_float=True),1000))
attrs=json.loads((data/'items_ins_v2.json').read_text());human=json.loads((data/'items_human_ins.json').read_text())
engine.DEFAULT_ATTR_PATH=str(data/'items_ins_v2.json');engine.HUMAN_ATTR_PATH=str(data/'items_human_ins.json')
engine.json=SimpleNamespace(load=lambda f:batch if Path(f.name).name=='items_shuffle.json' else attrs if Path(f.name).name=='items_ins_v2.json' else human)
random.seed(42)
products,*_=engine.load_products(str(data/'items_shuffle.json'))
source=ast.parse((ROOT/'vendor/WebShop/search_engine/convert_product_file_format.py').read_text())
loop=next(n for n in source.body if isinstance(n,ast.For))
scope={'all_products':products,'docs':[],'tqdm':lambda it,**kwargs:it}
exec(compile(ast.Module(body=[loop],type_ignores=[]),'<official-export-loop>','exec'),scope)
out=ROOT/'data/cache/webshop-search'
path=out/'resources/documents.jsonl'
if not path.exists():path=out/'documents.partial'
with path.open() as f:actual=[json.loads(next(f)) for _ in scope['docs']]
assert actual==scope['docs'],'Export differs from original converter'
result={'status':'passed','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'checked_documents':len(actual),'reference':'Unmodified author load_products and exact converter AST loop on first 1000 raw products','covers':'All document fields including nested product and retrieval contents; full corpus hash/count checked separately'}
(ROOT/'records/webshop_export_equivalence.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))

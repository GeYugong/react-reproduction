"""Bounded-memory adaptation of official convert_product_file_format.py.

Calls original load_products on chunks with shared original attribute mappings;
retains official fields, cleaning, filters, order, and Lucene indexing flags.
"""
from pathlib import Path
from datetime import datetime,timezone
from types import SimpleNamespace
import contextlib
import hashlib
import itertools
import json
import os
import random
import subprocess
import sys
import ijson

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/raw/webshop'
OUT=ROOT/'data/cache/webshop-search'

def save(r):
    r['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    p=ROOT/'records/webshop_index_preparation.json';t=p.with_suffix('.tmp')
    t.write_text(json.dumps(r,indent=2)+'\n');t.replace(p)

def main():
    java=json.loads((ROOT/'records/java_runtime.json').read_text())['java_home']
    os.environ['JAVA_HOME']=java
    os.environ['PATH']=java+'/bin:'+os.environ['PATH']
    os.environ['JVM_PATH']=java+'/lib/server/libjvm.so'
    os.environ['JAVA_TOOL_OPTIONS']='-Xmx6g'
    sys.path.insert(0,str(ROOT/'vendor/WebShop'))
    from web_agent_site.engine import engine
    attributes=json.loads((DATA/'items_ins_v2.json').read_text())
    human=json.loads((DATA/'items_human_ins.json').read_text())
    engine.DEFAULT_ATTR_PATH=str(DATA/'items_ins_v2.json')
    engine.HUMAN_ATTR_PATH=str(DATA/'items_human_ins.json')
    batch=[]
    def load_override(f):
        name=Path(f.name).name
        return batch if name=='items_shuffle.json' else attributes if name=='items_ins_v2.json' else human
    engine.json=SimpleNamespace(load=load_override)
    engine.print=lambda *args,**kwargs:None
    engine.tqdm=lambda iterable,**kwargs:iterable
    resources=OUT/'resources';resources.mkdir(parents=True,exist_ok=True)
    documents=resources/'documents.jsonl'
    marker=OUT/'export_manifest.json'
    r={'status':'exporting','source':'vendor/WebShop/search_engine/convert_product_file_format.py',
       'adapter':'Original engine.load_products in chunks of 1000; unchanged document text construction and Lucene flags.',
       'catalog':'full','product_count':0,'input_count':0,'java_home':java}
    save(r)
    if not marker.exists():
        random.seed(42)
        checksum=hashlib.sha256();seen=set()
        partial=OUT/'documents.partial'
        with (DATA/'items_shuffle.json').open('rb') as raw,partial.open('wb') as dest:
            iterator=ijson.items(raw,'item',use_float=True)
            while True:
                batch=list(itertools.islice(iterator,1000))
                if not batch:break
                r['input_count']+=len(batch)
                products,*_=engine.load_products(str(DATA/'items_shuffle.json'))
                for p in products:
                    if p['asin'] in seen:continue
                    seen.add(p['asin'])
                    option_texts=[]
                    for option_name,option_contents in p.get('options',{}).items():
                        option_texts.append(f"{option_name}: {', '.join(option_contents)}")
                    doc={'id':p['asin'],'contents':' '.join([p['Title'],p['Description'],p['BulletPoints'][0],', and '.join(option_texts)]).lower(),'product':p}
                    line=(json.dumps(doc)+'\n').encode('utf-8');dest.write(line);checksum.update(line)
                    r['product_count']+=1
                if r['input_count']%10000==0:save(r)
        assert r['input_count']==1181436
        partial.replace(documents)
        r['documents_sha256']=checksum.hexdigest();r['documents_bytes']=documents.stat().st_size
        marker.write_text(json.dumps(r,indent=2)+'\n')
    else:r.update(json.loads(marker.read_text()))
    r['status']='indexing';save(r)
    index=OUT/'indexes'
    if index.exists() and any(index.iterdir()):
        raise RuntimeError('Existing partial index requires explicit inspection before rebuilding')
    command=[sys.executable,'-m','pyserini.index.lucene','--collection','JsonCollection','--input',str(resources),
             '--index',str(index),'--generator','DefaultLuceneDocumentGenerator','--threads','1',
             '--storePositions','--storeDocvectors','--storeRaw']
    r['index_command']=command;save(r)
    subprocess.run(command,check=True)
    from pyserini.search.lucene import LuceneSearcher
    searcher=LuceneSearcher(str(index))
    assert searcher.num_docs==r['product_count']
    hits=searcher.search('apple cinnamon',k=5)
    r.update(status='index_built_search_smoke_passed',indexed_documents=searcher.num_docs,smoke_query='apple cinnamon',smoke_docids=[h.docid for h in hits])
    assert hits
    save(r)

if __name__=='__main__':
    try:main()
    except Exception as e:
        p=ROOT/'records/webshop_index_preparation.json'
        r=json.loads(p.read_text()) if p.exists() else {}
        r.update(status='stopped',error_type=type(e).__name__,error=str(e));save(r)
        raise

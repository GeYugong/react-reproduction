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
import re
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
    command=[sys.executable,'-m','pyserini.index.lucene','--collection','JsonCollection','--input',str(resources),
             '--index',str(index),'--generator','DefaultLuceneDocumentGenerator','--threads','1',
             '--storePositions','--storeDocvectors','--storeRaw']
    r['index_command']=command;save(r)
    if index.exists() and any(index.iterdir()):
        r['reused_existing_index']=True
    else:
        with (OUT/'index-build.log').open('w') as log:
            subprocess.run(command,check=True,stdout=log,stderr=subprocess.STDOUT)
        r['reused_existing_index']=False
    log_path=OUT/'index-build.log'
    if not log_path.exists():log_path=ROOT/'data/cache/webshop-index.stdout.log'
    log_text=log_path.read_text()
    counters={k:int(re.findall(r'\b'+k+r':\s*([\d,]+)',log_text)[-1].replace(',',''))
              for k in ['indexed','unindexable','empty','skipped','errors']}
    assert 'Indexing Complete!' in log_text and all(counters[k]==0 for k in ['unindexable','skipped','errors'])
    checksum=hashlib.sha256();empty=[];count=0
    with documents.open('rb') as f:
        for line in f:
            checksum.update(line);doc=json.loads(line);count+=1
            if not doc['contents'].strip():empty.append(doc['id'])
    assert count==r['product_count'] and checksum.hexdigest()==r['documents_sha256']
    assert len(empty)==counters['empty'] and count-len(empty)==counters['indexed']
    from pyserini.search.lucene import LuceneSearcher
    searcher=LuceneSearcher(str(index))
    assert searcher.num_docs==count-len(empty)
    assert all(searcher.doc(asin) is None for asin in empty)
    hits=searcher.search('apple cinnamon',k=5)
    index_files=[]
    for p in sorted(index.iterdir()):
        if p.is_file():
            h=hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
            index_files.append({'name':p.name,'bytes':p.stat().st_size,'sha256':h.hexdigest()})
    r.update(status='index_built_search_smoke_passed',indexed_documents=searcher.num_docs,
             empty_document_ids=empty,index_counters=counters,index_files=index_files,
             acceptance='All exported documents accounted for; only whitespace-only contents omitted by original Lucene generator. No product removed from the environment.',
             log_path=str(log_path.relative_to(ROOT)),log_sha256=hashlib.sha256(log_path.read_bytes()).hexdigest(),
             smoke_query='apple cinnamon',smoke_docids=[h.docid for h in hits])
    assert hits
    save(r)

if __name__=='__main__':
    previous=ROOT/'records/webshop_index_preparation.json'
    failure=ROOT/'records/webshop_index_initial_failure.json'
    if previous.exists() and not failure.exists():
        old=json.loads(previous.read_text())
        if old.get('status')=='stopped':failure.write_text(json.dumps(old,indent=2)+'\n')
    try:main()
    except Exception as e:
        p=ROOT/'records/webshop_index_preparation.json'
        r=json.loads(p.read_text()) if p.exists() else {}
        r.update(status='stopped',error_type=type(e).__name__,error=str(e));save(r)
        raise

"""Pinned full-corpus mirror fallback after original Drive URL returned 404.

Provenance and cross-mirror hashes:
https://huggingface.co/datasets/sparklabutah/timewarp-env-data/blob/main/README.md
https://huggingface.co/datasets/HongbangYuan/webshop/tree/0129d4a81dbdb827e76afd20a1e2c38b61098613
Mirrored source identity is disclosed; original Drive bytes are unavailable.
"""
import requests
from prepare_webshop_data import ROOT, DATA, sha
import json
from datetime import datetime, timezone

REV='0129d4a81dbdb827e76afd20a1e2c38b61098613'
BASE='https://huggingface.co/datasets/HongbangYuan/webshop/resolve/'+REV+'/'
FILES=[('items_human_ins.json',5137548,None),
       ('items_ins_v2.json',186295270,'1d36af476bdb8f82a5da62bd8acdabe54cd8de2fa84010d37da5c4890feb447e'),
       ('items_shuffle.json',5479720229,'2ef591d65df3af89e972ab72468eb82cbf124d876552d9f3678667edd620a6c8')]

def save(r):
    r['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    p=ROOT/'records/webshop_mirror_preparation.json';t=p.with_suffix('.tmp')
    t.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');t.replace(p)

def main():
    DATA.mkdir(parents=True,exist_ok=True)
    r={'status':'running','mirror':BASE,'original_failure_record':'records/webshop_data_preparation.json','files':[]}
    try:
        for name,size,expected in FILES:
            target=DATA/name;partial=DATA/(name+'.partial');r['current_file']=name;save(r)
            if not target.exists():
                offset=partial.stat().st_size if partial.exists() else 0
                with requests.get(BASE+name+'?download=true',headers={'Range':f'bytes={offset}-'} if offset else {},stream=True,timeout=(30,120)) as response:
                    response.raise_for_status()
                    if response.status_code==206:
                        if not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise RuntimeError('Unexpected range')
                    else:offset=0
                    with partial.open('ab' if offset else 'wb') as f:
                        for chunk in response.iter_content(4*1024*1024):
                            if chunk:f.write(chunk)
                            r['downloaded_bytes']=f.tell()
                            save(r)
                if partial.stat().st_size!=size:raise ValueError('Size mismatch')
                actual=sha(partial)
                if expected and actual!=expected:raise ValueError('SHA256 mismatch')
                partial.replace(target)
            actual=sha(target)
            if target.stat().st_size!=size or (expected and actual!=expected):raise ValueError('Existing file mismatch')
            r['files'].append({'path':str(target.relative_to(ROOT)),'bytes':size,'sha256':actual,'expected_sha256':expected,'url':BASE+name})
            save(r)
        r['status']='downloaded_full_schema_and_environment_validation_pending';save(r)
    except Exception as e:
        r.update(status='stopped',error_type=type(e).__name__,error=str(e));save(r);raise

if __name__=='__main__':main()

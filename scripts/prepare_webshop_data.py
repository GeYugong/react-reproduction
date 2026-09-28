"""Download full WebShop corpus using file IDs pinned in official setup.sh."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import gdown

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/raw/webshop'
FILES=[('1A2whVgOO0euk5O13n2iYDM0bQRkkRduB','items_shuffle.json'),
       ('1s2j6NgHljiZzQNL3veZaAiyW_qDEgBNi','items_ins_v2.json'),
       ('14Kb5SPBk_jfdLZ_CDBNitW98QLDlKR5O','items_human_ins.json')]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def save(record):
    record['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    p=ROOT/'records/webshop_data_preparation.json'
    t=p.with_suffix('.tmp');t.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');t.replace(p)

def main():
    DATA.mkdir(parents=True,exist_ok=True)
    record={'status':'running','source':'vendor/WebShop/setup.sh -d all','files':[],'python':'3.8.20 (patch update from original 3.8.13)'}
    try:
        for file_id,name in FILES:
            path=DATA/name
            record['current_file']=name;save(record)
            if not path.exists():
                partial=DATA/(name+'.partial')
                result=gdown.download(id=file_id,output=str(partial),quiet=False,resume=True)
                if not result:raise RuntimeError('gdown returned no file')
                # A successful HTTP response can still be an HTML error page.
                with partial.open('rb') as f:
                    if f.read(100).lstrip()[:1] not in [b'[',b'{']:raise ValueError('Downloaded file is not JSON')
                partial.replace(path)
            record['files'].append({'path':str(path.relative_to(ROOT)),'file_id':file_id,'bytes':path.stat().st_size,'sha256':sha(path)})
            save(record)
        record['status']='downloaded_schema_and_environment_validation_pending';save(record)
    except Exception as e:
        record.update(status='stopped',error_type=type(e).__name__,error=str(e));save(record);raise

if __name__=='__main__':main()

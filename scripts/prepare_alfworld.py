"""Use official ALFWorld downloader helpers for text-only data and logic."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import runpy
import shutil
import tempfile
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/raw/alfworld'
DATA.mkdir(parents=True,exist_ok=True)
os.environ['ALFWORLD_DATA']=str(DATA)
tmp=ROOT/'data/cache/download-temp'
tmp.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(tmp)
official=runpy.run_path(str(ROOT/'vendor/alfworld/scripts/alfworld-download'))

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def save(value):
    path=ROOT/'records/alfworld_data_preparation.json'
    value['updated_at_utc']=datetime.now(timezone.utc).isoformat()
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)

def main():
    record={'status':'running','source':'vendor/alfworld/scripts/alfworld-download',
            'adaptation':'Official download/unzip helpers; only text data, retain archives; no visual detector or trained agents.', 'archives':[]}
    try:
        for name in ['JSON_FILES_URL','PDDL_FILES_URL','TW_PDDL_FILES_URL']:
            url=official[name]
            record['current_url']=url; save(record)
            filename=Path(official['download'](url,str(DATA)))
            with zipfile.ZipFile(filename) as archive:
                for entry in archive.infolist():
                    if not (DATA/entry.filename).resolve().is_relative_to(DATA.resolve()):
                        raise ValueError('Archive member outside data directory')
                if archive.testzip():raise ValueError('ZIP integrity failure')
            official['unzip'](str(filename),str(DATA))
            record['archives'].append({'url':url,'path':str(filename.relative_to(ROOT)),'bytes':filename.stat().st_size,'sha256':sha(filename)})
            save(record)
        logic=DATA/'logic';logic.mkdir(exist_ok=True)
        shutil.copyfile(official['ALFRED_PDDL_PATH'],logic/'alfred.pddl')
        shutil.copyfile(official['ALFRED_TWL2_PATH'],logic/'alfred.twl2')
        gamefiles=sorted((DATA/'json_2.1.1/valid_unseen').rglob('game.tw-pddl'))
        record.update(status='data_downloaded_runtime_validation_pending',unseen_game_files=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p)} for p in gamefiles],unseen_game_count=len(gamefiles))
        save(record)
    except Exception as e:
        record.update(status='stopped',error_type=type(e).__name__,error=str(e));save(record);raise

if __name__=='__main__':main()

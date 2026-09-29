"""Install verified Temurin Java 11 under project envs without global changes."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import tarfile
import requests

ROOT=Path(__file__).resolve().parents[1]
API='https://api.adoptium.net/v3/assets/latest/11/hotspot?architecture=x64&image_type=jdk&os=linux&vendor=eclipse'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main():
    response=requests.get(API,timeout=45);response.raise_for_status()
    asset=response.json()[0];package=asset['binary']['package']
    archive=ROOT/'data/cache'/package['name']
    if not archive.exists():
        partial=archive.with_suffix('.partial')
        with requests.get(package['link'],stream=True,timeout=(30,120)) as r:
            r.raise_for_status()
            with partial.open('wb') as f:
                for chunk in r.iter_content(1024*1024):
                    if chunk:f.write(chunk)
        if sha(partial)!=package['checksum']:raise ValueError('JDK checksum mismatch')
        partial.replace(archive)
    assert sha(archive)==package['checksum']
    target=ROOT/'envs/java';target.mkdir(parents=True,exist_ok=True)
    with tarfile.open(archive) as tar:
        members=tar.getmembers()
        for member in members:
            if not (target/member.name).resolve().is_relative_to(target.resolve()):raise ValueError('Unsafe archive path')
        java_home=target/members[0].name.split('/')[0]
        if not (java_home/'bin/java').exists():tar.extractall(target,filter='data')
    result=subprocess.run([str(java_home/'bin/java'),'-version'],capture_output=True,text=True,check=True)
    record={'status':'java11_verified','recorded_at_utc':datetime.now(timezone.utc).isoformat(),'java_home':str(java_home),
            'download_url':package['link'],'sha256':package['checksum'],'release':asset['release_name'],'version_output':result.stderr,
            'scope':'project-local runtime; no global environment configuration changed'}
    (ROOT/'records/java_runtime.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record))

if __name__=='__main__':main()

"""Extract the original ReAct WebShop HTML parser and action state machine."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
notebook=ROOT/'vendor/ReAct/WebShop.ipynb'
cells=json.loads(notebook.read_text())['cells']
source=next(''.join(c['source']) for c in cells if 'def webshop_text(' in ''.join(c['source']))
source=source.replace('WEBSHOP_URL = "http://3.83.245.205:3000"',
                      'WEBSHOP_URL = "http://127.0.0.1:3000"\nHTTP_GET = requests.get')
source=source.replace('    html = requests.get(url).text',
                      '    response = HTTP_GET(url)\n    response.raise_for_status()\n    html = response.text')
source=source.replace('env = webshopEnv()','')
source='\n'.join(line.rstrip() for line in source.splitlines()).rstrip()+'\n'
target=ROOT/'src/react_reproduction/author/webshop_env.py'
target.write_text('"""ReAct WebShop.ipynb extraction (MIT, see LICENSE in this directory).\n'
                  'Pinned revision 6bdb3a1fd38b8188fc7ba4102969fe483df8fdc9.\n'
                  'Adaptations: loopback URL, injectable HTTP getter and HTTP status check.\n"""\n'+source)
print(json.dumps({'path':str(target.relative_to(ROOT)),
                  'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}))

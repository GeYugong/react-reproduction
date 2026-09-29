"""Check decision accounting, author context window, and no reward leakage."""
from run_webshop import run_episode

class Log:
    def add(self,**event): pass

class Model:
    def __init__(self,actions): self.actions=iter(actions); self.prompts=[]
    def generate(self,prompt,*args): self.prompts.append(prompt); return next(self.actions)

class Env:
    def __init__(self): self.sessions={}; self.actions=[]
    def step(self,session,action):
        self.actions.append(action);self.sessions[session]={'page_type':'init'}
        return 'Instruction: task\n'+'observation '*1000, float(action=='click[Buy Now]'),action=='click[Buy Now]'

prefix='Original example\n'
model=Model(['think[plan]']+['search[query]']*13);env=Env()
result=run_episode(model,env,prefix,'react','test',Log())
assert len(model.prompts)==14 and len(env.actions)==15
assert len(result['trajectory'])==14 and result['termination']=='decision_limit'
assert all(len(p)==6400 and p.startswith(prefix) for p in model.prompts)
assert result['trajectory'][0]['observation']=='OK.'
model=Model(['think[plan]','Action: click[Buy Now]']);env=Env()
result=run_episode(model,env,prefix,'act','test',Log())
assert env.actions==['reset','click[Buy Now]']
assert result['trajectory'][0]['error']=='invalid_action'
assert result['success'] and len(model.prompts)==2
assert all('Your score' not in p for p in model.prompts)
print('14 decisions, reset accounting, 6400-char window, Act control, and stop-on-reward passed')

"""Offline checks for the author's sparse-thought and decision-limit semantics."""
from run_alfworld import run_episode

class Log:
    def add(self,**event):pass
class Model:
    def __init__(self):self.prompts=[]
    def generate(self,prompt,*args):
        self.prompts.append(prompt)
        return 'think: find the object' if len(self.prompts)==1 else 'look'
class Env:
    def __init__(self,success_at=None):self.n=0;self.success_at=success_at
    def step(self,actions):
        self.n+=1
        done=self.n==self.success_at
        return ['Room observation'],[0],[done],{'won':[done]}

model=Model();env=Env()
result=run_episode(model,env,'Examples\n','Task','react','test',Log())
assert len(result['trajectory'])==49 and env.n==49 and not result['won']
assert 'OK.' in model.prompts[1] and len(model.prompts)==49
model=Model();env=Env(success_at=3)
result=run_episode(model,env,'Examples\n','Task','react','test',Log())
assert result['won'] and len(result['trajectory'])==3
print('Sparse thoughts, 49-decision limit, and environment success checks passed')

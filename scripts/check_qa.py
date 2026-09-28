import sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from run_qa import parse_action, vote, final_answer, WikiEnv
from types import SimpleNamespace
assert parse_action('Thought 1: find\nAction 1: Search[Amber]\nObservation 1: invented',1,'react')=='search[Amber]'
assert parse_action('Thought 1: no\nAction 1: Finish[x]',1,'act') is None
assert parse_action('Action 2: Finish[x]',1,'react') is None
assert parse_action('Action 4: Search[Prudential Center]',4,'react') == 'search[Prudential Center]'
assert vote(['yes','no','NO','YES'],'hotpotqa')==('yes',2)
assert vote(['bad']*21,'fever')==('',0)
assert final_answer('Reasoning\nAnswer: London','cot')=='London'
e=WikiEnv(lambda url:SimpleNamespace(text='<p>Amber is on shelf K-17. It belongs to the archive.</p>'))
e.reset();e.step('search[Amber]');assert 'K-17' in e.step('lookup[shelf]')[0]
assert e.step('finish[K-17]')[2]
print('Offline parser, voting, and author Search/Lookup/Finish checks passed')

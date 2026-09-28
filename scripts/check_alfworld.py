from pathlib import Path
import os,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
os.environ['ALFWORLD_DATA']=str(ROOT/'data/raw/alfworld')
import yaml
from alfworld.agents.environment import get_environment
c=yaml.safe_load((ROOT/'vendor/ReAct/base_config.yaml').read_text())
c['general']['use_cuda']=False
for k,v in c['dataset'].items():
 if isinstance(v,str):c['dataset'][k]=os.path.expandvars(v)
for k,v in c['logic'].items():c['logic'][k]=os.path.expandvars(v)
manager=get_environment('AlfredTWEnv')(c,train_eval='eval_out_of_distribution')
assert manager.num_games==134,manager.num_games
files=sorted(manager.game_files)
manager.game_files=files
(Path(ROOT/'configs/alfworld-runtime.json')).write_text(json.dumps(c,indent=2)+'\n')
env=manager.init_env(batch_size=1)
obs,info=env.reset()
step=env.step(['look'])
result={'status':'reset_and_step_passed','num_games':len(files),'game_files':[{'path':str(Path(p).relative_to(ROOT)),'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest()} for p in files],'first_reset_observation':obs,'first_game':info.get('extra.gamefile'),'look_observation':step[0],'source_config':'vendor/ReAct/base_config.yaml','changes':['CPU only','Project-local absolute data paths','Sorted gamefile order'],'no_model_calls':True}
(ROOT/'records/alfworld_runtime_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
env.close()
print('ALFWorld 134 game inventory, reset and look passed')

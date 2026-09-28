"""Adapted from author's alfworld.ipynb (MIT): sparse thoughts, 49 decisions."""
import argparse
import json
import os
from pathlib import Path
from run_qa import ROOT, Client, Journal, digest, now, write_json

PREFIXES={'pick_and_place':'put','pick_clean_then_place':'clean','pick_heat_then_place':'heat',
          'pick_cool_then_place':'cool','look_at_obj':'examine','pick_two_obj':'puttwo'}

def process_ob(ob):
    if ob.startswith('You arrive at loc '):ob=ob[ob.find('. ')+2:]
    return ob

def run_episode(client,env,prompt,ob,method,episode_id,journal):
    context=prompt+ob+'\n>'
    trajectory=[]
    for i in range(1,50):
        output=client.generate(context,method,f'alfworld/{episode_id}/{method}/{i}',['\n'])
        action=output.strip()
        # Chat continuation may repeat the final '>' prefix; remove only this syntax.
        if action.startswith('>'):action=action[1:].lstrip()
        observation,reward,done,info=env.step([action])
        raw_ob=observation[0]
        observation=process_ob(raw_ob)
        won=bool(info['won'][0]);done=bool(done[0])
        if action.startswith('think:'):observation='OK.'
        step={'step':i,'raw_output':output,'action':action,'raw_observation':raw_ob,
              'observation':observation,'won':won,'done':done}
        trajectory.append(step)
        journal.add(event='alfworld_step',episode_id=episode_id,method=method,**step)
        context+=f' {action}\n{observation}\n>'
        if done:return {'won':won,'termination':'environment_done','trajectory':trajectory}
    return {'won':False,'termination':'decision_limit','trajectory':trajectory}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['pilot','formal'],default='pilot')
    parser.add_argument('--limit',type=int,default=2)
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    if not args.run_id.replace('-','').replace('_','').isalnum():raise ValueError('Invalid run ID')
    if args.phase=='formal' and not args.dry_run:
        audit=ROOT/'records/alfworld_pilot_audit.json'
        if not audit.exists() or json.loads(audit.read_text()).get('status')!='passed':
            raise RuntimeError('ALFWorld model pilot has not been audited')
    gate=ROOT/'records/billing_gate.json'
    if not args.dry_run and gate.exists() and json.loads(gate.read_text())['status']=='requires_user_billing_action':
        raise RuntimeError('API billing blocked; no paid dispatch attempted')
    os.environ['ALFWORLD_DATA']=str(ROOT/'data/raw/alfworld')
    from alfworld.agents.environment import get_environment
    config=json.loads((ROOT/'configs/alfworld-runtime.json').read_text())
    api_config=json.loads((ROOT/'configs/experiment.json').read_text())
    prompts=json.loads((ROOT/'prompts/alfworld_3prompts.json').read_text())
    split='eval_in_distribution' if args.phase=='pilot' else 'eval_out_of_distribution'
    manager=get_environment('AlfredTWEnv')(config,train_eval=split)
    all_files=sorted(manager.game_files)
    if args.phase=='formal':
        expected=json.loads((ROOT/'records/alfworld_runtime_check.json').read_text())['game_files']
        assert len(all_files)==134 and [str(Path(p).relative_to(ROOT)) for p in all_files]==[e['path'] for e in expected]
        for p,e in zip(all_files,expected):assert digest(Path(p).read_bytes())==e['sha256']
        if args.limit!=134:raise ValueError('Formal ALFWorld must include all 134 games')
    assert 0<args.limit<=len(all_files)
    manager.game_files=all_files[:args.limit]
    folder=ROOT/'runs/raw'/args.run_id
    journal=Journal(folder/'events.jsonl')
    fingerprint={'phase':args.phase,'dry_run':args.dry_run,'gamefiles':manager.game_files,'config':config,'api_config':api_config,
                 'source_sha256':digest(Path(__file__).read_bytes()),'prompts_sha256':digest((ROOT/'prompts/alfworld_3prompts.json').read_bytes())}
    if (folder/'manifest.json').exists():
        assert json.loads((folder/'manifest.json').read_text())['fingerprint']==fingerprint
    else:write_json(folder/'manifest.json',{'started_at_utc':now(),'fingerprint':fingerprint,'dry_run':args.dry_run})
    client=None if args.dry_run else Client(api_config,folder,journal)
    completed=0
    for method in ['act','react']:
        env=manager.init_env(batch_size=1)
        try:
            for idx,path in enumerate(manager.game_files):
                ob,info=env.reset()
                actual=Path(info['extra.gamefile'][0])
                if actual.resolve()!=Path(path).resolve():raise RuntimeError('Environment game order mismatch')
                name='/'.join(actual.parts[-3:-1])
                key=next(v for k,v in PREFIXES.items() if name.startswith(k))
                prompt='Interact with a household to solve a task. Here are two examples.\n'+prompts[f'{method}_{key}_1']+prompts[f'{method}_{key}_0']+'\nHere is the task.\n'
                observation='\n'.join(ob[0].split('\n\n')[1:])
                eid=digest(str(actual.relative_to(ROOT)).encode())[:16]
                path_out=folder/'episodes'/f'{eid}-{method}.json'
                if args.dry_run:
                    journal.add(event='dry_reset',method=method,gamefile=str(actual),prompt_sha256=digest(prompt.encode()),observation=observation)
                elif not path_out.exists():
                    result=run_episode(client,env,prompt,observation,method,eid,journal)
                    write_json(path_out,{'dataset':'alfworld','method':method,'gamefile':str(actual),'task':observation,'phase':args.phase,**result})
                completed+=1
                write_json(ROOT/'records'/(args.run_id+'.json'),{'status':'running','phase':args.phase,'completed':completed,'planned':args.limit*2,'dry_run':args.dry_run,'updated_at_utc':now()})
        finally:env.close()
    write_json(ROOT/'records'/(args.run_id+'.json'),{'status':'completed','phase':args.phase,'completed':completed,'planned':args.limit*2,'dry_run':args.dry_run,'updated_at_utc':now()})

if __name__=='__main__':main()

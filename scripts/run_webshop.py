"""ReAct author WebShop loop: fixed prompt, 6400 chars, 14 executed decisions."""
import argparse
import copy
import json
from pathlib import Path
import re
import requests
from urllib.parse import quote
from run_qa import ROOT, Client, Journal, digest, now, write_json
from react_reproduction.author import webshop_env as original


def run_episode(client, env, prompt, method, session, journal, window=6400, decisions=14):
    observation, reward, done = env.step(session, 'reset')
    task=observation
    history=observation+'\n\nAction:'
    trajectory=[]
    journal.add(event='webshop_reset',session=session,observation=observation,
                state=copy.deepcopy(env.sessions[session]))
    assert 0 < len(prompt) < window
    for step in range(1,decisions+1):
        context=prompt+history[-(window-len(prompt)):]
        journal.add(event='webshop_context',session=session,step=step,history_characters=len(history),
                    sent_characters=len(context),truncated_characters=max(0,len(history)-(window-len(prompt))),
                    context_sha256=digest(context.encode()))
        output=client.generate(context,method,f'webshop/{session}/{step}',['\n'])
        action=output.strip().split('\n')[0]
        if action.startswith('Action:'): action=action[len('Action:'):].lstrip()
        before=copy.deepcopy(env.sessions[session])
        error=None
        try:
            assert re.fullmatch(r'(think|search|click)\[.*\]',action)
            assert method!='act' or not action.startswith('think[')
            observation,reward,done=env.step(session,action)
        except AssertionError:
            observation,reward,done='Invalid action!',0.0,False
            error='invalid_action'
        raw_observation=observation
        if method=='react' and action.startswith('think[') and error is None: observation='OK.'
        entry={'step':step,'raw_output':output,'action':action,'state_before':before,
               'state_after':copy.deepcopy(env.sessions[session]),'raw_observation':raw_observation,
               'observation':observation,'reward':reward,'done':bool(done),'error':error}
        trajectory.append(entry)
        journal.add(event='webshop_step',session=session,method=method,**entry)
        history+=f' {action}\nObservation: {observation}\n\nAction:'
        if done:
            return {'task':task,'reward':float(reward),'success':reward==1,
                    'termination':'environment_done','trajectory':trajectory}
    return {'task':task,'reward':0.0,'success':False,'termination':'decision_limit','trajectory':trajectory}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--phase',choices=['pilot','formal'],default='pilot')
    p.add_argument('--run-id',required=True)
    p.add_argument('--config',type=Path,required=True)
    args=p.parse_args()
    assert re.fullmatch(r'[A-Za-z0-9_-]+',args.run_id)
    config=json.loads(args.config.read_text())
    assert config['model']['id']=='qwen3.6-35b-a3b'
    if args.phase=='formal':
        audit=json.loads((ROOT/'records/webshop_pilot_audit.json').read_text())
        assert audit['status']=='passed' and audit['model']==config['model']['id']
    targets=json.loads((ROOT/'data/webshop_eval_goals.json').read_text())
    selected=targets['formal' if args.phase=='formal' else 'pilot']
    health=requests.get(original.WEBSHOP_URL+'/_reproduction_health',timeout=60)
    health.raise_for_status()
    assert health.json()['goals_sha256']==targets['source_manifest']['goals_sha256']
    prompts=json.loads((ROOT/'prompts/webshop.json').read_text())
    folder=ROOT/'runs/raw'/args.run_id
    journal=Journal(folder/'events.jsonl')
    files=['scripts/run_webshop.py','scripts/run_qa.py','scripts/webshop_runtime.py','scripts/serve_webshop.py',
           'src/react_reproduction/author/webshop_env.py','prompts/webshop.json']
    fingerprint={'phase':args.phase,'config':config,'targets':selected,'environment':targets['source_manifest'],
                 'sources':{f:digest((ROOT/f).read_bytes()) for f in files}}
    manifest=folder/'manifest.json'
    if manifest.exists(): assert json.loads(manifest.read_text())['fingerprint']==fingerprint
    else:
        write_json(manifest,{'started_at_utc':now(),'fingerprint':fingerprint})
        for f in files:
            dst=folder/'source'/f;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes((ROOT/f).read_bytes())
    client=Client(config,folder,journal)
    def get(url):
        response=requests.get(quote(url, safe=":/"),timeout=60)
        journal.add(event='webshop_http',url=url,resolved_url=response.url,http_status=response.status_code,
                    html=response.text,html_sha256=digest(response.content))
        return response
    original.HTTP_GET=get
    completed=0
    record=ROOT/'records'/(args.run_id+'.json')
    state={'status':'running','run_id':args.run_id,'phase':args.phase,'model':config['model']['id'],
           'completed':0,'planned':2*len(selected)}
    try:
        for method in ['act','react']:
            prompt=prompts['prompt1_actonly' if method=='act' else 'prompt1']
            for target in selected:
                index=target['goal_index']
                path=folder/'episodes'/f'{index}-{method}.json'
                if not path.exists():
                    # Unique method session; fixed suffix preserves author goal mapping.
                    session=f'{args.run_id}_{method}_fixed_{index}'
                    result=run_episode(client,original.webshopEnv(),prompt,method,session,journal,
                                       config['datasets']['webshop']['prompt_window_characters'],
                                       config['datasets']['webshop']['max_decisions'])
                    assert target['instruction_text'] in result['task']
                    write_json(path,{'dataset':'webshop','index':index,'method':method,'model':client.model,
                                     'goal_sha256':target['goal_sha256'],'phase':args.phase,**result})
                completed+=1
                state.update(completed=completed,updated_at_utc=now(),last={'index':index,'method':method})
                write_json(record,state)
        state.update(status='completed',updated_at_utc=now());write_json(record,state)
    except Exception as e:
        state.update(status='stopped',completed=completed,error_type=type(e).__name__,error=str(e),updated_at_utc=now())
        write_json(record,state);raise


if __name__=='__main__': main()

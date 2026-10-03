"""Replay the stopped ALFWorld prefix offline before a documented source revision.

No model requests. Original response and manifest are retained, never resampled.
Use --apply only after reviewing the recorded compatibility rule.
"""
import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch
from interactive_protocol import InteractiveClient, isolated_marker, nonempty_reasoning
from run_alfworld import PREFIXES, run_episode
from run_qa import ROOT, Journal, digest, now, write_json


class ReplayComplete(Exception): pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-id', required=True)
    p.add_argument('--apply', action='store_true')
    args = p.parse_args()
    folder = ROOT/'runs/raw'/args.run_id
    manifest = json.loads((folder/'manifest.json').read_text())
    fp = manifest['fingerprint']
    config = fp['api_config']
    evidence_path = ROOT/'records/alfworld-reasoning-stop-20261002T0352.json'
    evidence = json.loads(evidence_path.read_text())
    assert evidence['run_id'] == args.run_id
    response_event = evidence['response_evidence']
    call_id = response_event['call_id']
    _, eid, method, step = call_id.split('/')
    step = int(step)
    assert isolated_marker(response_event['response'], config['model']['id'])
    rows = [json.loads(line) for line in (folder/'events.jsonl').open()]
    dispatch = {r['call_id']: r for r in rows if r['event'] == 'api_dispatch'}
    assert any(r == response_event for r in rows)
    previous = [r for r in rows if r['event'] == 'alfworld_step'
                and r['episode_id'] == eid and r['method'] == method]
    assert [r['step'] for r in previous] == list(range(1, step))
    assert not (folder/'episodes'/f'{eid}-{method}.json').exists()
    outputs = {r['step']: r['raw_output'] for r in previous}
    outputs[step] = response_event['response']['choices'][0]['message']['content']
    config_path = ROOT/'configs/alfworld-qwen36-formal.json'
    assert json.loads(config_path.read_text()) == config
    gamefiles = fp['gamefiles']
    target = next(path for path in gamefiles if digest(str(Path(path).relative_to(ROOT)).encode())[:16] == eid)
    for path in gamefiles:
        assert digest(Path(path).read_bytes()) == fp['game_sha256'][str(Path(path).relative_to(ROOT))]
    assert digest((ROOT/'scripts/run_qa.py').read_bytes()) == fp['client_sha256']
    assert digest((ROOT/'prompts/alfworld_3prompts.json').read_bytes()) == fp['prompts_sha256']
    old_episodes = {p.name: digest(p.read_bytes()) for p in (folder/'episodes').glob('*.json')}
    stats = {'success_responses': 0, 'isolated_markers': 0, 'malformed_http200': 0}
    for row in rows:
        if row['event'] != 'api_response' or row['http_status'] != 200: continue
        body = row['response']
        if 'non_json_response' in body:
            try: json.loads(body['non_json_response'])
            except ValueError: stats['malformed_http200'] += 1; continue
            raise AssertionError('Valid JSON misclassified as malformed')
        assert body['model'] == config['model']['id'] and not nonempty_reasoning(body)
        content = body['choices'][0]['message'].get('content') or ''
        if '<think' in content.lower() or '<analysis' in content.lower():
            assert isolated_marker(body, config['model']['id']) and row['call_id'] == call_id
            stats['isolated_markers'] += 1
        else: stats['success_responses'] += 1
    assert stats['isolated_markers'] == 1
    replay = []
    class Log:
        def add(self, **record): replay.append(record)
    class Model:
        def generate(self, prompt, actual_method, actual_call, stop):
            n = int(actual_call.rsplit('/', 1)[-1])
            assert actual_method == method and stop == ['\n']
            if n == step + 1: raise ReplayComplete()
            assert actual_call == f'alfworld/{eid}/{method}/{n}'
            assert prompt == dispatch[actual_call]['request']['messages'][-1]['content']
            return outputs[n]
    os.environ['ALFWORLD_DATA'] = str(ROOT/'data/raw/alfworld')
    from alfworld.agents.environment import get_environment
    manager = get_environment('AlfredTWEnv')(fp['config'], train_eval='eval_out_of_distribution')
    assert sorted(manager.game_files) == gamefiles
    manager.game_files = gamefiles
    env = manager.init_env(batch_size=1)
    env.seed(config['evaluation']['bootstrap_seed'])
    try:
        for index in range(len(gamefiles)):
            obs, info = env.reset()
            if info['extra.gamefile'][0] == target: break
        else: raise AssertionError('Target not in frozen reset sequence')
        name = '/'.join(Path(target).parts[-3:-1])
        key = next(v for k, v in PREFIXES.items() if name.startswith(k))
        prompts = json.loads((ROOT/'prompts/alfworld_3prompts.json').read_text())
        prompt = 'Interact with a household to solve a task. Here are two examples.\n'+prompts[f'{method}_{key}_1']+prompts[f'{method}_{key}_0']+'\nHere is the task.\n'
        ob = '\n'.join(obs[0].split('\n\n')[1:])
        with patch('run_qa.requests.post', side_effect=AssertionError('Offline replay must not call model')):
            try: run_episode(Model(), env, prompt, ob, method, eid, Log())
            except ReplayComplete: pass
    finally: env.close()
    assert len(replay) == step
    for original, actual in zip(previous, replay):
        assert {k: v for k, v in original.items() if k != 'timestamp_utc'} == actual
    invalid = replay[-1]
    assert invalid['raw_output'] == invalid['executed_action'] == '<think>'
    assert invalid['raw_observation'] == invalid['observation'] == 'Nothing happens.'
    assert invalid['reward'] == 0 and not invalid['won'] and not invalid['done']
    assert old_episodes == {p.name: digest(p.read_bytes()) for p in (folder/'episodes').glob('*.json')}
    record = {'timestamp_utc': now(), 'run_id': args.run_id, 'status': 'offline_verified',
              'rule': 'Exact standalone <think>, finish_reason=stop, unchanged model, and no nonempty recursive reasoning telemetry: consume literal as invalid action; never resample or strip; all other reasoning still stops',
              'scope': 'ALFWorld Act/ReAct; explicit post-freeze protocol compatibility revision, not a generation-parameter change',
              'call_id': call_id, 'raw_evidence': str(evidence_path.relative_to(ROOT)),
              'replayed_prior_steps': step-1, 'invalid_step': invalid,
              'prior_episode_count': len(old_episodes), 'prior_episode_sha256': old_episodes,
              'response_scan': stats, 'prior_manifest': manifest,
              'source_sha256': digest((ROOT/'scripts/run_alfworld.py').read_bytes()),
              'interactive_protocol_sha256': digest((ROOT/'scripts/interactive_protocol.py').read_bytes()),
              'config_sha256': digest(config_path.read_bytes()), 'paid_calls_in_validation': 0,
              'limitations': 'Isolated markup is not proof of native reasoning being enabled or disabled; absent upstream telemetry and immutable weight identity remain unknown. Report the protocol revision.'}
    record_path = ROOT/'records/alfworld-isolated-marker-revision.json'
    if args.apply:
        assert not record_path.exists(), 'Do not overwrite an existing revision'
        old_source = folder/'run_alfworld.source.py'
        assert digest(old_source.read_bytes()) == fp['source_sha256']
        backup = folder/'run_alfworld.before-isolated-marker.py'
        assert not backup.exists()
        backup.write_bytes(old_source.read_bytes())
        # An offline placeholder satisfies construction; no request is dispatched.
        with patch.dict(os.environ, {'AIGW_API_KEY': 'offline-validation'}):
            client = InteractiveClient(config, folder, Journal(folder/'events.jsonl'))
            request = dispatch[call_id]['request']
            rejection = client.preserve_marker(request['messages'][-1]['content'], method, call_id,
                                               request.get('stop'), request, response_event)
        record['rejection_artifact'] = str(rejection.relative_to(ROOT))
        record['rejection_sha256'] = digest(rejection.read_bytes())
        # Write the old manifest evidence before replacing the live source fingerprint.
        write_json(record_path, record)
        revised = json.loads(json.dumps(manifest))
        revised['fingerprint']['source_sha256'] = record['source_sha256']
        revised['fingerprint']['interactive_protocol_sha256'] = record['interactive_protocol_sha256']
        old_source.write_bytes((ROOT/'scripts/run_alfworld.py').read_bytes())
        (folder/'interactive_protocol.source.py').write_bytes((ROOT/'scripts/interactive_protocol.py').read_bytes())
        write_json(folder/'manifest.json', revised)
        Journal(folder/'events.jsonl').add(event='protocol_compatibility_revision', record=str(record_path.relative_to(ROOT)),
                                          original_call_preserved=call_id, no_resampling=True)
    print(json.dumps({k: record[k] for k in ['status', 'run_id', 'replayed_prior_steps', 'prior_episode_count', 'response_scan', 'paid_calls_in_validation']}))


if __name__ == '__main__': main()

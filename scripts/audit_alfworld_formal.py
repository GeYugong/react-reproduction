"""Offline formal audit using the author's frozen TextWorld environment.

Replays every decision without API access; retains all failed games and the
explicit isolated-marker compatibility revision. Runner provenance: see
run_alfworld.py and the vendored author's MIT license.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re
from unittest.mock import patch

from interactive_protocol import nonempty_reasoning, isolated_marker
from run_alfworld import PREFIXES, run_episode
from run_qa import ROOT, digest, now, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    folder = ROOT/'runs/raw'/args.run_id
    fp = json.loads((folder/'manifest.json').read_text())['fingerprint']
    cfg = fp['api_config']
    assert fp['phase'] == 'formal' and not fp['dry_run']
    assert cfg == json.loads((ROOT/'configs/alfworld-qwen36-formal.json').read_text())
    state = json.loads((ROOT/'records'/(args.run_id+'.json')).read_text())
    assert state['status'] == 'completed' and state['completed'] == state['planned'] == 268
    for file, key in [('scripts/run_alfworld.py', 'source_sha256'),
                      ('scripts/run_qa.py', 'client_sha256'),
                      ('scripts/interactive_protocol.py', 'interactive_protocol_sha256'),
                      ('prompts/alfworld_3prompts.json', 'prompts_sha256')]:
        assert digest((ROOT/file).read_bytes()) == fp[key]
    for file, h in fp['game_sha256'].items():
        assert digest((ROOT/file).read_bytes()) == h
    episodes = {}
    for p in (folder/'episodes').glob('*.json'):
        e = json.loads(p.read_text())
        key = (e['episode_id'], e['method'])
        assert key not in episodes
        episodes[key] = e
        assert e['model'] == cfg['model']['id'] and e['phase'] == 'formal'
    assert len(episodes) == 268
    revision = json.loads((ROOT/'records/alfworld-isolated-marker-revision.json').read_text())
    for file, h in revision['prior_episode_sha256'].items():
        assert digest((folder/'episodes'/file).read_bytes()) == h
    requests, responses, steps = {}, {}, {}
    events, finishes, usage = Counter(), Counter(), Counter()
    markers = malformed = 0
    for line in (folder/'events.jsonl').open():
        row = json.loads(line); events[row['event']] += 1
        cid = row.get('call_id')
        if row['event'] == 'api_dispatch' and 'request' in row:
            payload = row['request']
            if cid in requests:
                assert requests[cid] == payload
            requests[cid] = payload
        if row['event'] == 'alfworld_step':
            key = (row['episode_id'], row['method'], row['step'])
            actual = {k: v for k, v in row.items() if k not in ['timestamp_utc', 'event', 'episode_id', 'method']}
            if key in steps:
                assert steps[key] == actual
            steps[key] = actual
        if row['event'] != 'api_response' or row['http_status'] != 200:
            continue
        b = row['response']
        if 'non_json_response' in b:
            try:
                json.loads(b['non_json_response'])
            except ValueError:
                malformed += 1
                continue
            raise AssertionError('Incorrect malformed response classification')
        assert b['model'] == cfg['model']['id'] and not nonempty_reasoning(b)
        assert len(b['choices']) == 1
        c = b['choices'][0]; m = c['message']
        assert not m.get('tool_calls') and not m.get('function_call')
        content = m.get('content') or ''
        if re.search(r'<think\b|<analysis\b', content, re.I):
            assert cid == revision['call_id'] and isolated_marker(b, cfg['model']['id'])
            markers += 1
        assert cid not in responses, 'Repeated successful generation must be investigated'
        responses[cid] = content
        finishes[c['finish_reason']] += 1
        assert b.get('usage')
        for k in ['prompt_tokens', 'completion_tokens', 'total_tokens']:
            usage[k] += b['usage'][k]
    assert markers == 1
    assert len(responses) == sum(len(e['trajectory']) for e in episodes.values())
    for (eid, method), e in episodes.items():
        assert 1 <= len(e['trajectory']) <= 49
        for n, t in enumerate(e['trajectory'], 1):
            assert t['step'] == n and steps[eid, method, n] == t
            assert responses[f'alfworld/{eid}/{method}/{n}'] == t['raw_output']
    os.environ['ALFWORLD_DATA'] = str(ROOT/'data/raw/alfworld')
    from alfworld.agents.environment import get_environment
    manager = get_environment('AlfredTWEnv')(fp['config'], train_eval='eval_out_of_distribution')
    assert sorted(manager.game_files) == fp['gamefiles']
    manager.game_files = fp['gamefiles']
    prompts = json.loads((ROOT/'prompts/alfworld_3prompts.json').read_text())
    replayed = 0
    class Log:
        def add(self, **record):
            pass
    class Model:
        def generate(self, prompt, method, cid, stop):
            expected = {'model': cfg['model']['id'], 'messages': [
                {'role': 'system', 'content': 'Continue the provided text exactly from its final prefix. Do not repeat the prefix or earlier examples.'},
                {'role': 'user', 'content': prompt}],
                'temperature': cfg['generation']['default_temperature'],
                'top_p': cfg['generation']['top_p'],
                'max_tokens': cfg['generation']['max_output_tokens'][method],
                **cfg['model']['requested_controls'], 'stream': False, 'stop': stop}
            assert requests[cid] == expected, cid
            return responses[cid]
    with patch('run_qa.requests.post', side_effect=AssertionError('Audit cannot call model')):
        for method in ['act', 'react']:
            env = manager.init_env(batch_size=1)
            env.seed(cfg['evaluation']['bootstrap_seed'])
            seen = set()
            try:
                for _ in range(134):
                    obs, info = env.reset()
                    path = Path(info['extra.gamefile'][0])
                    assert str(path) in fp['gamefiles'] and str(path) not in seen
                    seen.add(str(path))
                    eid = digest(str(path.relative_to(ROOT)).encode())[:16]
                    e = episodes[eid, method]
                    assert e['gamefile'] == str(path)
                    ob = '\n'.join(obs[0].split('\n\n')[1:])
                    assert e['task'] == ob
                    name = '/'.join(path.parts[-3:-1])
                    key = next(v for k, v in PREFIXES.items() if name.startswith(k))
                    prompt = 'Interact with a household to solve a task. Here are two examples.\n'+prompts[f'{method}_{key}_1']+prompts[f'{method}_{key}_0']+'\nHere is the task.\n'
                    result = run_episode(Model(), env, prompt, ob, method, eid, Log())
                    assert all(result[k] == e[k] for k in result), (eid, method)
                    replayed += 1
                    write_json(ROOT/'records'/(args.run_id+'-audit-progress.json'),
                               {'status': 'running', 'replayed': replayed, 'planned': 268, 'updated_at_utc': now()})
            finally:
                env.close()
    report = {'status': 'passed', 'run_id': args.run_id, 'timestamp_utc': now(),
              'episodes': replayed, 'successful_responses': len(responses),
              'environment_steps': len(steps), 'finish_reasons': dict(finishes),
              'events': dict(events), 'usage': dict(usage), 'isolated_marker_responses': markers,
              'malformed_http200': malformed, 'paid_audit_calls': 0,
              'cost_status': 'pending_reconciliation', 'actual_cost_cny': None,
              'native_reasoning_missing_telemetry': 'unknown',
              'immutable_weight_identity': 'unverified_gateway_alias',
              'protocol_revision': 'records/alfworld-isolated-marker-revision.json',
              'manifest_sha256': digest((folder/'manifest.json').read_bytes()),
              'events_sha256': digest((folder/'events.jsonl').read_bytes()),
              'episode_sha256': {p.name: digest(p.read_bytes()) for p in (folder/'episodes').glob('*.json')},
              'audit_source_sha256': digest(Path(__file__).read_bytes())}
    write_json(ROOT/'records'/(args.run_id+'-audit.json'), report)
    print(json.dumps({k:v for k,v in report.items() if k != 'episode_sha256'}))


if __name__ == '__main__':
    main()

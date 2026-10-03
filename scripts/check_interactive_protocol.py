"""Offline transport fixtures for the isolated-marker compatibility rule."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from interactive_protocol import InteractiveClient, isolated_marker
from run_alfworld import run_episode
from run_qa import ROOT, Journal, ProtocolError


def body(content='<think>'):
    return {'model': 'qwen3.6-35b-a3b', 'choices': [
        {'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': content}}],
        'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5}}


class Response:
    status_code = 200
    def __init__(self, value): self.value = value
    def json(self): return self.value
    def raise_for_status(self): pass


class Env:
    def __init__(self): self.actions = []
    def step(self, actions):
        self.actions.extend(actions)
        done = len(self.actions) == 2
        return ['Nothing happens.' if not done else 'Task complete.'], [int(done)], [done], {'won': [done]}


def main():
    config = json.loads((ROOT/'configs/alfworld-qwen36-formal.json').read_text())
    negative = [body('<think>some reasoning'), body('<analysis>'), body(' <think>')]
    for location in ('message', 'usage', 'nested'):
        item = body()
        if location == 'message': item['choices'][0]['message']['reasoning_content'] = 'reason'
        if location == 'usage': item['usage']['completion_tokens_details'] = {'reasoning_tokens': 1}
        if location == 'nested': item['provider'] = {'analysis': {'text': 'reason'}}
        negative.append(item)
    item = body(); item['model'] = 'other-model'; negative.append(item)
    item = body(); item['choices'][0]['finish_reason'] = 'length'; negative.append(item)
    assert all(not isolated_marker(item, config['model']['id']) for item in negative)
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'AIGW_API_KEY': 'offline-test'}):
        folder = Path(directory)
        client = InteractiveClient(config, folder, Journal(folder/'events.jsonl'))
        with patch('run_qa.requests.post', return_value=Response(body())) as post:
            assert client.generate('Task\n>', 'react', 'isolated/1', ['\n']) == '<think>'
            assert post.call_count == 1
        assert not list((folder/'responses').glob('*.json'))
        with patch('run_qa.requests.post', side_effect=AssertionError('No resampling allowed')):
            assert client.generate('Task\n>', 'react', 'isolated/1', ['\n']) == '<think>'
            try: client.generate('Changed task', 'react', 'isolated/1', ['\n'])
            except AssertionError: pass
            else: raise AssertionError('Context mismatch must be rejected')
        for i, item in enumerate(negative):
            with patch('run_qa.requests.post', return_value=Response(deepcopy(item))) as post:
                try: client.generate('Task', 'react', f'negative/{i}', ['\n'])
                except ProtocolError: pass
                else: raise AssertionError('Non-isolated reasoning must still stop')
                assert post.call_count == 1
        for method in ('act', 'react'):
            env = Env()
            with patch('run_qa.requests.post', side_effect=[Response(body()), Response(body('look'))]) as post:
                result = run_episode(client, env, 'Examples\n', 'Task', method, method, Journal(folder/'steps.jsonl'))
                assert post.call_count == 2 and len(result['trajectory']) == 2
                assert env.actions == ['<think>', 'look']
                assert result['trajectory'][0]['observation'] == 'Nothing happens.'
                assert '<think>' in result['trajectory'][0]['raw_output']
    print('PASS: literal action, real step count, no resampling, context guard, recursive native reasoning/identity stops')


if __name__ == '__main__': main()

"""Preserve an isolated <think> response as a literal invalid environment action.

This documented interactive-protocol revision never resamples or repairs output.
Nonempty reasoning telemetry, markup with content, and identity errors still stop.
Rejected responses remain outside the successful-response cache.
"""
import json
from run_qa import Client, ProtocolError, digest, write_json


def nonempty_reasoning(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if any(word in key.lower() for word in ('reasoning', 'thinking', 'analysis')):
                if item not in (None, False, 0, '', 'none', [], {}):
                    return True
            if nonempty_reasoning(item):
                return True
    elif isinstance(value, list):
        return any(nonempty_reasoning(item) for item in value)
    return False


def isolated_marker(body, model):
    choices = body.get('choices') or []
    if body.get('model') != model or nonempty_reasoning(body) or len(choices) != 1:
        return False
    choice = choices[0]
    message = choice.get('message') or {}
    return (choice.get('finish_reason') == 'stop'
            and message.get('content') == '<think>'
            and not message.get('tool_calls') and not message.get('function_call'))


class CaptureJournal:
    def __init__(self, journal):
        self.journal = journal
        self.captured = {}

    def add(self, **record):
        self.journal.add(**record)
        if record.get('event') in ('api_dispatch', 'api_response'):
            self.captured[record['event']] = record
        if (record.get('event') == 'api_response' and record.get('http_status') == 200
                and nonempty_reasoning(record.get('response'))):
            raise ProtocolError('Unexpected native reasoning telemetry; batch stopped')


class InteractiveClient(Client):
    def __init__(self, config, folder, journal):
        self.capture = CaptureJournal(journal)
        super().__init__(config, folder, self.capture)

    def _path(self, call_id):
        return self.folder / 'protocol_rejections' / (digest(call_id.encode()) + '.json')

    def preserve_marker(self, prompt, method, call_id, stop, request, response_event):
        """Used for both live rejection and explicitly verified historical replay."""
        body = response_event['response']
        assert response_event['call_id'] == call_id and response_event['http_status'] == 200
        assert isolated_marker(body, self.model)
        cfg = self.config['generation']
        assert request['messages'][-1] == {'role': 'user', 'content': prompt}
        expected = {'model': self.model, 'temperature': cfg['default_temperature'],
                    'top_p': cfg['top_p'], 'max_tokens': cfg['max_output_tokens'][method],
                    'stream': False, **self.config['model']['requested_controls']}
        assert method in ('act', 'react') and request.get('stop') == stop
        assert all(request.get(k) == v for k, v in expected.items())
        record = {'call_id': call_id, 'method': method, 'stop': stop,
                  'config_sha256': digest(json.dumps(self.config, sort_keys=True).encode()),
                  'request': request, 'response_event': response_event,
                  'handling': 'literal_invalid_action_no_resample',
                  'native_reasoning_identity_limit': 'Missing telemetry remains unknown'}
        path = self._path(call_id)
        if path.exists():
            assert json.loads(path.read_text()) == record
        else:
            write_json(path, record)
        return path

    def _consume(self, path, prompt, method, call_id, stop, replay):
        record = json.loads(path.read_text())
        assert record['call_id'] == call_id and record['method'] == method
        assert record['stop'] == stop
        assert record['config_sha256'] == digest(json.dumps(self.config, sort_keys=True).encode())
        assert record['request']['messages'][-1] == {'role': 'user', 'content': prompt}
        body = record['response_event']['response']
        assert isolated_marker(body, self.model)
        self.journal.add(event='isolated_marker_invalid_action', call_id=call_id,
                         replay=replay, artifact=str(path.relative_to(self.folder)),
                         sha256=digest(path.read_bytes()), raw_output=body['choices'][0]['message']['content'],
                         resampled=False, successful_response_cache=False)
        return body['choices'][0]['message']['content']

    def generate(self, prompt, method, call_id, stop=None):
        path = self._path(call_id)
        if path.exists():
            return self._consume(path, prompt, method, call_id, stop, replay=True)
        self.capture.captured = {}
        try:
            return super().generate(prompt, method, call_id, stop)
        except ProtocolError as exc:
            response = self.capture.captured.get('api_response', {})
            if (str(exc) != 'Unexpected reasoning markup; batch stopped'
                    or response.get('call_id') != call_id
                    or not isolated_marker(response.get('response', {}), self.model)):
                raise
            request = self.capture.captured['api_dispatch']['request']
            path = self.preserve_marker(prompt, method, call_id, stop, request, response)
            return self._consume(path, prompt, method, call_id, stop, replay=False)

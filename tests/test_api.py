"""API 경계 테스트: 실제 AI 호출 없이 SQLite/업로드/스트리밍을 검증한다."""
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, SystemMessage

ROOT = Path(__file__).resolve().parents[1] / 'Integrated_agent'


def module(name, path, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, value)
    spec.loader.exec_module(value)
    return value


@pytest.fixture
def api(tmp_path, monkeypatch):
    config = types.ModuleType('config')
    for key, value in dict(MAX_UPLOAD_MB=1, UPLOAD_DIR=tmp_path/'uploads', OUTPUT_DIR=tmp_path/'output',
                           OPENAI_API_KEY='test-only', TYPESAFE_API_KEY='', NAVER_CLIENT_ID='',
                           NAVER_CLIENT_SECRET='', OPENAI_MODEL='mock', JEV_MODEL='mock').items():
        setattr(config, key, value)
    config.UPLOAD_DIR.mkdir()
    config.OUTPUT_DIR.mkdir()
    monkeypatch.setitem(sys.modules, 'config', config)
    utils = types.ModuleType('file_utils')
    utils.ALLOWED_UPLOAD_EXTENSIONS = {'.txt', '.png'}
    monkeypatch.setitem(sys.modules, 'file_utils', utils)
    usage = module('usage_tracking', ROOT/'usage_tracking.py', monkeypatch)
    store = module('chat_store', ROOT/'chat_store.py', monkeypatch)
    store.DB_PATH = tmp_path/'chat.sqlite3'
    agent = types.ModuleType('agent')
    agent.ALL_TOOLS = []
    agent.TOOL_LABELS = {}
    agent.create_messages = lambda: [SystemMessage(content='test')]

    def stream(question, history, files, force_judgment=False, continue_case=False):
        usage.record_usage('OpenAI', 'mock', 'chat', {'input_tokens': 3, 'output_tokens': 2})
        usage.record_usage('NAVER API HUB', 'news', 'request', note='tokens unavailable')
        yield {'type': 'status', 'text': 'working'}
        yield {'type': 'reset'}
        yield {'type': 'token', 'text': '답변'}
        if question == 'report':
            path = config.OUTPUT_DIR/'report.txt'
            path.write_text('generated report')
            yield {'type': 'tool_result', 'name': 'create_report', 'label': '보고서',
                   'data': {'성공': True, '파일 경로': str(path)}}
            raise RuntimeError('mock failure after output')
        if question == 'flags':
            assert force_judgment and continue_case
        yield {'type': 'done', 'answer': '답변', 'messages': [*history, HumanMessage(content=question)]}
    agent.stream_agent = stream
    monkeypatch.setitem(sys.modules, 'agent', agent)
    server = module('server', ROOT/'server.py', monkeypatch)
    with TestClient(server.app) as client:
        yield client, server, store


def test_history_isolated_and_persistent(api):
    client, _, store = api
    a = client.post('/chats').json()['chat_id']
    b = client.post('/chats').json()['chat_id']
    r = client.post('/chat', json={'message': 'hello', 'chat_id': a})
    assert r.status_code == 200
    assert len(client.get(f'/chats/{a}').json()['turns']) == 1
    assert client.get(f'/chats/{b}').json()['turns'] == []
    assert store.load_chat(a)['turns'][0]['answer'] == '답변'


def test_stream_flags_and_usage(api):
    client, _, _ = api
    chat = client.post('/chats').json()['chat_id']
    response = client.post('/chat/stream', json={'chat_id': chat, 'message': 'flags',
                            'force_judgment': True, 'continue_case': True})
    events = [json.loads(row) for row in response.text.splitlines()]
    assert events[-1]['type'] == 'done'
    assert events[-1]['turn']['answer'] == '답변'
    data = client.get('/usage', params={'chat_id': chat}).json()
    assert data['summary'][0]['합계'] == '5'
    assert data['summary'][1]['합계'] == '확인 불가'
    assert data['records'][1]['total_tokens'] is None


def test_upload_dedupe_download_and_size(api):
    client, server, _ = api
    chat = client.post('/chats').json()['chat_id']
    for _ in range(2):
        r = client.post(f'/chats/{chat}/files', files={'file': ('../sample.txt', b'hello')})
        assert r.status_code == 200
        assert len(r.json()['files']) == 1
    assert client.get(r.json()['files'][0]['url']).content == b'hello'
    assert len(list(server.UPLOAD_DIR.iterdir())) == 1
    assert client.post(f'/chats/{chat}/files', files={'file': ('x.txt', b'x'*(1024*1024+1))}).status_code == 413
    assert len(list(server.UPLOAD_DIR.iterdir())) == 1
    assert client.post(f'/chats/{chat}/files', files={'file': ('x.exe', b'x')}).status_code == 400
    assert client.get(f'/chats/{chat}/files/-1').status_code == 404


def test_error_preserves_report_and_usage(api):
    client, _, store = api
    chat = client.post('/chats').json()['chat_id']
    r = client.post('/chat/stream', json={'message': 'report', 'chat_id': chat})
    last = json.loads(r.text.splitlines()[-1])
    assert last['type'] == 'done' and last['turn']['error']
    assert len(last['turn']['usage']) == 2
    file = last['turn']['files'][0]
    assert client.get(file['url']).text == 'generated report'
    assert store.load_chat(chat)['turns'][0]['error']


def test_reject_arbitrary_download(api, tmp_path):
    client, _, store = api
    chat = client.post('/chats').json()['chat_id']
    secret = tmp_path/'outside.txt'
    secret.write_text('outside')
    state = store.load_chat(chat)
    state['files'].append({'name': 'outside', 'path': str(secret)})
    store.save_chat(state)
    assert client.get(f'/chats/{chat}/files/0').status_code == 404
    assert client.get(f'/chats/{chat}').json()['files'] == []


def test_busy_and_unknown_chat(api):
    client, server, _ = api
    server.chat_lock.acquire()
    try:
        assert client.post('/chats').status_code == 409
        assert client.post('/chat/stream', json={'message': 'hello'}).status_code == 409
    finally:
        server.chat_lock.release()
    assert client.get('/chats/missing').status_code == 404
    assert client.post('/chat', json={'message': '   '}).status_code == 400


def test_save_failure_surfaces_error(api, monkeypatch):
    client, server, _ = api
    chat = client.post('/chats').json()['chat_id']
    def fail(_):
        raise RuntimeError('disk unavailable')
    monkeypatch.setattr(server, 'save_chat', fail)
    r = client.post('/chat/stream', json={'message': 'hello', 'chat_id': chat})
    last = json.loads(r.text.splitlines()[-1])
    assert last['type'] == 'error'
    assert last['turn']['answer'] == '답변'
    assert not server.chat_lock.locked()

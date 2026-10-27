import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from google.genai import types, errors
import httpx
from google import genai

from app.config import Settings
from app.main import create_app
from app.services.chat import ChatLimiter, ChatService
from app.services.summary import summarize
from app.store import LocalStore

HEADERS = {"X-Session-ID": "test-browser-session-0123456789abcdef"}
OTHER = {"X-Session-ID": "other-browser-session-0123456789abcdef"}


@pytest.fixture
def client(tmp_path):
    settings = Settings(demo=True, local_path=tmp_path / "demo.json", chat_per_minute=100)
    with TestClient(create_app(settings)) as test:
        test.headers.update(HEADERS)
        yield test


def test_original_data_and_summary(client):
    assert client.get('/docs').status_code == 200
    assert client.get('/health').json()['demo'] is True
    summary = client.get('/api/data/summary').json()
    assert summary['count'] == 731
    assert summary['metrics']['total'] == 3292679
    assert summary['metrics']['average'] == 4504.35
    assert summary['metrics']['max'] == 8714
    assert summary['metrics']['min_date'] == '2012-10-29'
    assert len(summary['monthly']) == 24
    assert summary['as_of'] == '2012-12-31'
    listing = client.get('/api/data?limit=2&offset=1').json()
    assert listing['total'] == 731
    assert len(listing['items']) == 2
    assert listing['items'][0]['date'] == '2012-12-30'


def test_crud_updates_summary_and_persists(client):
    payload = {'date':'2013-01-01','value':3000,'memo':'새해 기록'}
    created = client.post('/api/data', json=payload)
    assert created.status_code == 201
    assert client.post('/api/data', json=payload).status_code == 409
    payload.update(date='2013-01-02', value=5000, memo='수정된 기록')
    updated = client.put('/api/data/2013-01-01', json=payload)
    assert updated.status_code == 200
    assert updated.json()['created_at'] == created.json()['created_at']
    assert updated.json()['id'] == '2013-01-02'
    summary = client.get('/api/data/summary').json()
    assert summary['count'] == 732 and summary['metrics']['total'] == 3297679
    persisted = LocalStore(client.app.state.settings.local_path)
    assert persisted.get('data','2013-01-02')['memo'] == '수정된 기록'
    assert client.delete('/api/data/2013-01-02').status_code == 204
    assert client.delete('/api/data/2013-01-02').status_code == 404
    assert client.get('/api/data/summary').json()['metrics']['total'] == 3292679


@pytest.mark.parametrize('patch', [
    {'date':'2012-02-30'}, {'value':-1}, {'value':1.5}, {'value':True},
    {'value':'3000'}, {'value':10000001}, {'memo':'x'*501}, {'unexpected':123},
])
def test_bad_data_rejected(client, patch):
    assert client.post('/api/data', json={'date':'2013-01-01','value':1, **patch}).status_code == 422


def test_data_conflict_and_filters(client):
    assert client.put('/api/data/2012-12-31', json={'date':'2012-12-30','value':10}).status_code == 409
    assert client.put('/api/data/2015-01-01', json={'date':'2015-01-02','value':10}).status_code == 404
    result = client.get('/api/data?start=2012-12-01&end=2012-12-31&limit=100').json()
    assert result['total'] == 31
    assert client.get('/api/data?start=2013-01-01&end=2012-01-01').status_code == 422
    assert client.get('/api/data?offset=-1').status_code == 422


def test_conversation_save_load_and_isolation(client):
    record = {'title':'직접 저장한 대화','messages':[{'role':'user','content':'질문'},{'role':'assistant','content':'답변'}]}
    saved = client.post('/api/conversations', json=record)
    assert saved.status_code == 201
    id = saved.json()['id']
    assert 'owner' not in saved.json()
    listed = client.get('/api/conversations').json()
    assert listed[0]['message_count'] == 2
    assert 'messages' not in listed[0]
    assert client.get('/api/conversations/'+id).json()['messages'] == record['messages']
    assert client.get('/api/conversations', headers=OTHER).json() == []
    assert client.get('/api/conversations/'+id, headers=OTHER).status_code == 404
    assert client.delete('/api/conversations/'+id, headers=OTHER).status_code == 404
    assert client.delete('/api/conversations/'+id).status_code == 204
    assert client.get('/api/conversations/'+id).status_code == 404


def test_chat_auto_save_continue_and_changed_context(client):
    first = client.post('/api/chat', json={'message':'전체 기록을 요약해 줘'})
    assert first.status_code == 200
    body = first.json()
    assert body['demo'] is True
    assert '[데모' in body['answer']
    id = body['conversation']['id']
    assert len(client.get('/api/conversations/'+id).json()['messages']) == 2
    client.put('/api/data/2012-09-15', json={'date':'2012-09-15','value':9900})
    second = client.post('/api/chat', json={'message':'최대 대여량은?', 'conversation_id':id})
    assert second.status_code == 200
    assert '9,900' in second.json()['answer']
    assert second.json()['summary']['metrics']['max'] == 9900
    assert second.json()['conversation']['revision'] == 2
    assert len(second.json()['conversation']['messages']) == 4
    assert client.post('/api/chat', headers=OTHER, json={'message':'안녕','conversation_id':id}).status_code == 404


def test_bad_chat_and_session(client):
    assert client.post('/api/chat', json={'message':'   '}).status_code == 422
    assert client.post('/api/chat', json={'message':'x'*2001}).status_code == 422
    assert client.post('/api/chat', json={'message':'안녕','conversation_id':'../../etc/passwd'}).status_code == 422
    assert client.get('/api/conversations', headers={'X-Session-ID':'short'}).status_code == 422


def test_summary_empty_missing_days_and_zero_baseline():
    empty = summarize([])
    assert empty['metrics']['average'] is None
    json.dumps(empty, allow_nan=False)
    start = date(2024,1,1)
    rows = [{'date':(start+timedelta(days=i)).isoformat(),'value':100 if i<7 else 200} for i in range(14)]
    assert summarize(rows)['recent']['change_percent'] == 100
    assert summarize(rows[1:])['recent']['change_percent'] is None
    zeroes = [{**r, 'value':0} for r in rows]
    assert summarize(zeroes)['recent']['change_percent'] is None
    assert summarize(rows)['metrics']['max_date'] == '2024-01-08'


def test_revision_conflict_prevents_overwrite(tmp_path):
    db = LocalStore(tmp_path/'db.json', seed=False)
    db.save('conversations','a',{'revision':1,'messages':[]})
    db.save('conversations','a',{'revision':2,'messages':['first']},expected=1)
    with pytest.raises(HTTPException) as error:
        db.save('conversations','a',{'revision':2,'messages':['overwritten']},expected=1)
    assert error.value.status_code == 409
    assert db.get('conversations','a')['messages'] == ['first']


def test_real_service_passes_context_history_and_token_cap(tmp_path):
    settings = Settings(demo=False,gemini_key='unit-test-key',local_path=tmp_path/'db.json')
    service = ChatService(settings)
    service.client.close()
    response = Mock(return_value=SimpleNamespace(
        candidates=[SimpleNamespace(finish_reason=types.FinishReason.STOP)], text='검증용 Gemini 답변'))
    service.client = SimpleNamespace(models=SimpleNamespace(generate_content=response),close=lambda:None)
    database = LocalStore(settings.local_path)
    with TestClient(create_app(settings, database, service)) as test:
        test.headers.update(HEADERS)
        first = test.post('/api/chat',json={'message':'기록을 요약해 줘'}).json()
        test.post('/api/chat',json={'message':'최고 기록은?','conversation_id':first['conversation']['id']})
        args = response.call_args.kwargs
        assert args['model'] == 'gemini-3.8-flash'
        assert args['config'].max_output_tokens == 800
        assert args['config'].thinking_config.thinking_level == types.ThinkingLevel.LOW
        assert '3292679' in args['config'].system_instruction
        assert 'as_of' in args['config'].system_instruction
        assert len(args['contents']) == 3
        assert args['contents'][1].role == 'model'
        assert args['contents'][1].parts[0].text == '검증용 Gemini 답변'
        assert args['contents'][2].parts[0].text == '최고 기록은?'


def test_upstream_failure_does_not_save_partial_conversation(client):
    client.app.state.chat.answer = Mock(side_effect=HTTPException(504,'AI 응답 지연'))
    assert client.post('/api/chat',json={'message':'질문'}).status_code == 504
    assert client.get('/api/conversations').json() == []


def test_rate_limit_and_cors(client):
    client.app.state.chat.limiter = ChatLimiter(1,100)
    assert client.post('/api/chat',json={'message':'첫 질문'}).status_code == 200
    assert client.post('/api/chat',json={'message':'두 번째 질문'}).status_code == 429
    good = client.options('/api/chat',headers={'Origin':'http://localhost:3000',
        'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'X-Session-ID,Content-Type'})
    assert good.headers['access-control-allow-origin'] == 'http://localhost:3000'
    bad = client.options('/api/chat',headers={'Origin':'https://untrusted.example',
        'Access-Control-Request-Method':'POST'})
    assert 'access-control-allow-origin' not in bad.headers


def test_production_requires_key(tmp_path):
    with pytest.raises(RuntimeError, match='GEMINI_API_KEY'):
        with TestClient(create_app(Settings(local_path=tmp_path/'db.json'))):
            pass


@pytest.mark.parametrize('error,expected', [
    (errors.ClientError(429, {'error':{'message':'quota'}}),429),
    (errors.ClientError(403, {'error':{'message':'denied'}}),503),
    (errors.ClientError(404, {'error':{'message':'unknown model'}}),503),
    (errors.ClientError(400, {'error':{'message':'bad request'}}),502),
    (errors.ServerError(503, {'error':{'message':'unavailable'}}),502),
    (httpx.ReadTimeout('timeout'),504),
])
def test_gemini_errors_are_actionable(error, expected):
    service = ChatService(Settings(gemini_key='unit-test-key'))
    service.client.close()
    service.client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(side_effect=error)))
    with pytest.raises(HTTPException) as result:
        service.answer([{'role':'user','content':'질문'}],summarize([]))
    assert result.value.status_code == expected


@pytest.mark.parametrize('reason,text', [(types.FinishReason.MAX_TOKENS,'불완전'),
    (types.FinishReason.SAFETY,''), (types.FinishReason.STOP,'')])
def test_gemini_incomplete_or_empty_response_rejected(reason, text):
    service = ChatService(Settings(gemini_key='unit-test-key'))
    service.client.close()
    service.client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock(
        return_value=SimpleNamespace(candidates=[SimpleNamespace(finish_reason=reason)],text=text))))
    with pytest.raises(HTTPException) as result:
        service.answer([{'role':'user','content':'질문'}],summarize([]))
    assert result.value.status_code == 502


def test_gemini_sdk_serializes_real_request_without_network():
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        assert request.url.path.endswith('/models/gemini-3.8-flash:generateContent')
        return httpx.Response(200, json={'candidates':[{
            'content':{'role':'model','parts':[{'text':'실제 SDK 직렬화 검증'}]},
            'finishReason':'STOP',
        }]})

    service = ChatService(Settings(gemini_key='unit-test-key'))
    service.client.close()
    service.client = genai.Client(api_key='unit-test-key', http_options=types.HttpOptions(
        client_args={'transport':httpx.MockTransport(handle)},
        retry_options=types.HttpRetryOptions(attempts=1),
    ))
    try:
        result = service.answer([{'role':'user','content':'이전 질문'},
            {'role':'assistant','content':'이전 답변'}, {'role':'user','content':'최신 질문'}], summarize([]))
    finally:
        service.client.close()
    assert result == '실제 SDK 직렬화 검증'
    assert len(captured) == 1
    body = captured[0]
    assert body['contents'][0]['role'] == 'user'
    assert body['contents'][1]['role'] == 'model'
    assert body['contents'][2]['parts'][0]['text'] == '최신 질문'
    assert '사용자 데이터 요약' in body['systemInstruction']['parts'][0]['text']
    assert body['generationConfig']['maxOutputTokens'] == 800
    assert body['generationConfig']['thinkingConfig']['thinking_level'] == 'LOW'

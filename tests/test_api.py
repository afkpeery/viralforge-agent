from fastapi.testclient import TestClient
from viralforge import app as agent
from viralforge.storage import Store

def test_core_endpoints(monkeypatch,tmp_path):
    monkeypatch.setattr(agent.settings,'agent_api_key','private-test-key')
    monkeypatch.setattr(agent,'store',Store(str(tmp_path/'api.db')))
    client=TestClient(agent.app)
    assert client.get('/health').status_code==200
    payload={'platform':'tiktok','niche':'filmmaking','topic':'shooting a film',
             'hook':'How to shoot better','caption':'This is how we shoot films.'}
    assert client.post('/api/analyze',json=payload).status_code==401
    headers={'X-Agent-Key':'private-test-key'}
    r=client.post('/api/analyze',json=payload,headers=headers)
    assert r.status_code==200, r.text
    assert 'reach_model' in r.json() and 'conversion_model' in r.json()
    assert r.json()['data_quality']['fresh_trend_count']==0
    assert client.post('/api/campaigns',headers=headers,json={
        'campaign_id':'brand_launch','variant_id':'a','platform':'tiktok',
        'destination':'https://example.com/landing?x=1'}).status_code==200
    response=client.get('/go/brand_launch/a',follow_redirects=False)
    assert response.status_code==302
    assert 'utm_content=a' in response.headers['location']
    assert 'x=1' in response.headers['location']
    assert client.post('/api/campaigns/exposure',headers=headers,json={
        'campaign_id':'brand_launch','variant_id':'a','views':1000}).status_code==200
    event={'event_id':'order-2026-001','campaign_id':'brand_launch','variant_id':'a','revenue':25}
    assert client.post('/api/events/conversion',headers=headers,json=event).json()['recorded']
    assert client.post('/api/events/conversion',headers=headers,json=event).json()['duplicate']
    stats=client.get('/api/campaigns/brand_launch/optimize',headers=headers).json()['variants']
    assert stats[0]['clicks']==1 and stats[0]['conversions']==1


def test_youtube_shorts_draft_duration_feedback(monkeypatch, tmp_path):
    monkeypatch.setattr(agent.settings, 'agent_api_key', 'private-test-key')
    monkeypatch.setattr(agent, 'store', Store(str(tmp_path / 'shorts.db')))
    client = TestClient(agent.app)
    draft = {
        'platform': 'youtube', 'niche': 'filmmaking', 'topic': 'Lighting a scene',
        'hook': 'Light a scene with one lamp', 'caption': 'A one-light setup',
    }
    headers = {'X-Agent-Key': 'private-test-key'}
    for duration, format_fit in [(180, 100), (181, 0)]:
        response = client.post('/api/analyze', headers=headers,
                               json={**draft, 'duration_seconds': duration})
        assert response.status_code == 200, response.text
        reach = response.json()['reach_model']
        assert reach['signals']['format_fit'] == format_fit
        assert any('vertical or square' in tip for tip in reach['recommendations'])
        assert any('180 seconds' in tip for tip in reach['recommendations']) == (duration > 180)

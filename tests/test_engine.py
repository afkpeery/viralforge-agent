from datetime import datetime,timezone,timedelta
import pytest
from viralforge.models import Draft,Trend,Observation,Campaign,ConversionEvent
from viralforge.engine import reach_analysis,conversion_analysis,hashtag_suggestions,choose_variants,train_reach
from viralforge.storage import Store

def draft(**kwargs):
    return Draft(platform='tiktok',niche='filmmaking',topic='filmmaking commercial shoot',
                 hook='How we filmed a commercial',caption='Here is our filmmaking process #filmmaking',**kwargs)

def test_trend_relevant_fresh_only():
    now=datetime.now(timezone.utc)
    fresh=Trend(platform='tiktok',hashtag='filmmaking',niche='filmmaking',region='US',
                observed_at=now,source='approved export',growth_24h=.5)
    stale=Trend(platform='tiktok',hashtag='filmmaking',niche='filmmaking',region='US',
                observed_at=now-timedelta(days=10),source='old data')
    unrelated=Trend(platform='tiktok',hashtag='gardening',niche='gardening',region='US',
                    observed_at=now,source='approved export')
    result=hashtag_suggestions(draft(),[stale,fresh,unrelated])
    assert result['recommended'][0]['hashtag']=='#filmmaking'
    assert result['recommended'][0]['live']
    assert '#gardening' not in [t['hashtag'] for t in result['recommended']]


def test_reach_and_conversion_are_distinct():
    base=draft()
    reach=reach_analysis(base,[],[])
    conversion=conversion_analysis(base)
    assert reach['estimated_top_quartile_probability'] is None
    assert reach['reach_readiness_score']!=conversion['conversion_readiness_score']
    better=draft(call_to_action='Book your consult',offer='Free brand audit',landing_page='https://example.com/book')
    assert conversion_analysis(better)['conversion_readiness_score']>conversion['conversion_readiness_score']


def test_training_threshold():
    posts=[Observation(platform='tiktok',post_id=str(i),caption=f'How to film video {i}',
                       views=1000+i*100) for i in range(10)]
    model,meta=train_reach(posts)
    assert model is None and not meta['trained']


def test_oauth_state_one_time_and_encrypted(tmp_path):
    from cryptography.fernet import Fernet
    db=Store(str(tmp_path/'local.db'))
    db.add_state('randomstate','tiktok')
    assert db.consume_state('randomstate','tiktok')
    assert not db.consume_state('randomstate','tiktok')
    key=Fernet.generate_key().decode()
    db.put_token('tiktok',{'access_token':'private'},key)
    assert db.get_token('tiktok',key)['access_token']=='private'
    assert b'private' not in (tmp_path/'local.db').read_bytes()


def test_conversion_events_idempotent_and_variant_ranking(tmp_path):
    db=Store(str(tmp_path/'local.db'))
    db.put_campaign(Campaign(campaign_id='launch',variant_id='a',platform='tiktok',destination='https://example.com'))
    db.put_campaign(Campaign(campaign_id='launch',variant_id='b',platform='tiktok',destination='https://example.com'))
    db.set_exposure('launch','a',1000);db.set_exposure('launch','b',1000)
    for i in range(50):db.record_click('launch','a')
    for i in range(10):db.record_click('launch','b')
    e=ConversionEvent(event_id='order_00001',campaign_id='launch',variant_id='a',revenue=100)
    assert db.record_conversion(e) is True
    assert db.record_conversion(e) is False
    stats=choose_variants(db.campaign_stats('launch'),value_per_conversion=100)
    assert stats[0]['variant']=='a'
    assert stats[0]['expected_conversions_per_1000_views']>stats[1]['expected_conversions_per_1000_views']


def test_momentum_requires_real_growth_windows():
    from viralforge.models import Snapshot
    from viralforge.engine import momentum_opportunities
    t=datetime.now(timezone.utc)
    rows=[]
    for ident,new in [('a',2000),('b',250),('c',200)]:
        rows.extend([Snapshot(platform='tiktok',post_id=ident,views=100,observed_at=t-timedelta(hours=2)),
                     Snapshot(platform='tiktok',post_id=ident,views=new,shares=50 if ident=='a' else 1,observed_at=t)])
    r=momentum_opportunities(rows)
    assert r['posts_compared']==3
    assert r['opportunities'][0]['post_id']=='a'
    assert r['opportunities'][0]['status']=='takeoff_candidate'
    assert 'follow-up' in r['opportunities'][0]['recommended_next_action']


def test_algorithm_audit_returns_cohorts_without_causal_claims():
    from viralforge.engine import algorithm_audit
    posts=[]
    for i in range(20):
        posts.append(Observation(platform='tiktok',post_id=f'id{i}',
            caption=('What a great video? #film #behindthescenes' if i<10 else 'A new clip'),
            duration_seconds=20 if i<10 else 80,views=10000 if i<10 else 1000))
    result=algorithm_audit(posts)
    assert result['ready']
    assert result['factors']
    assert 'NOT causal' in result['warning']

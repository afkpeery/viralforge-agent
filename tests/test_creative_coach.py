from viralforge.creative_coach import improvement_plan
from viralforge.link_analysis import classify_url

def test_all_five_platforms_have_distinct_advice():
    plans={p:improvement_plan(p,caption='How to improve your edits') for p in ('tiktok','instagram','x','facebook','youtube')}
    assert len({plans[p]['recommendations'][0]['focus'] for p in plans}) == 5
    assert all(len(v['recommendations']) >= 3 for v in plans.values())

def test_evidence_and_conversion_distinction():
    plan=improvement_plan('youtube',transcript='This is the opening line',goal='sales')
    assert plan['evidence_level']=='transcript_provided'
    assert any(r['focus']=='Conversion path' for r in plan['recommendations'])
    assert 'not guaranteed' in plan['disclaimer']

def test_missing_media_does_not_fake_inspection():
    plan=improvement_plan('tiktok')
    assert plan['evidence_level']=='no_content_available'
    assert any(r['focus']=='Add evidence' for r in plan['recommendations'])

def test_urls_classified_for_five_platforms():
    urls=['https://www.tiktok.com/@creator/video/7345678901234567890','https://www.instagram.com/reel/ABC123/','https://x.com/creator/status/123456789','https://www.facebook.com/reel/12345','https://www.youtube.com/watch?v=abcdefghijk']
    assert {classify_url(u)['platform'] for u in urls}=={'tiktok','instagram','x','facebook','youtube'}

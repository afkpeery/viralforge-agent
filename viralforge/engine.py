"""Separate reach and conversion objectives; all scores explain their evidence."""
from __future__ import annotations
import math
import re
from collections import Counter
from datetime import datetime, timezone
from statistics import median
from typing import Iterable
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from .models import Draft, Trend, Observation, Snapshot

STOP={'the','and','for','with','this','that','will','you','your','are','has','was','from','how','what','but','into','about','just','our','now','not','its','can','all','out','have','it','why','a','an','or','of','to','in','on','is','my','we','be'}
WORDS=re.compile(r'[a-z0-9]+')

def terms(text):
    return set(WORDS.findall(text.lower())) - STOP

def similarity(a, b):
    a=terms(a);b=terms(b)
    if not a or not b:return 0.0
    return len(a & b)/len(a | b)

def clamp(v, lo=0, hi=1):
    return max(lo,min(hi,float(v)))

def trend_rank(trend:Trend, draft:Draft, now=None):
    now=now or datetime.now(timezone.utc)
    at=trend.observed_at.replace(tzinfo=timezone.utc) if trend.observed_at.tzinfo is None else trend.observed_at
    age_hours=max(0,(now-at).total_seconds()/3600)
    freshness=math.exp(-age_hours/36)
    context=' '.join([draft.niche,draft.community,draft.topic,draft.caption,draft.script,draft.audience])
    keyword=trend.hashtag.lstrip('#').replace('_',' ')
    context_terms=terms(context)
    tokens=terms(keyword)
    topic_overlap=len(tokens & context_terms)/max(1,len(tokens))
    niche_match=similarity(trend.niche, draft.niche)
    community_match=similarity(trend.community, draft.community)
    relevance=max(topic_overlap, 0.75*niche_match, 0.85*community_match)
    momentum=clamp((trend.growth_24h or 0)/1.5) if trend.growth_24h is not None else 0.20
    social_proof=clamp(math.log10(1+(trend.views or 0))/9) if trend.views else 0.25
    # Recency + topical relevance matter more than raw worldwide popularity.
    score=100*freshness*(0.12 + .60*relevance + .20*momentum + .08*social_proof)
    return {'hashtag':trend.hashtag, 'score':round(score,1),
            'relevance':round(relevance,2),'freshness':round(freshness,2),
            'growth_24h':trend.growth_24h, 'observed_at':at.isoformat(),
            'source':trend.source, 'age_hours':round(age_hours,1),
            'live':age_hours<=24, 'niche':trend.niche, 'community':trend.community}

def top_trends(trends, platform, region, niche='', community='', limit=15):
    # Only newest observation of a tag; old trends decay rather than becoming current.
    newest={}
    for t in trends:
        if t.platform!=platform or t.region.upper()!=region.upper():continue
        existing=newest.get(t.hashtag)
        if existing is None or t.observed_at>existing.observed_at:newest[t.hashtag]=t
    sample=Draft(platform=platform,niche=niche or 'general',topic=niche or community or 'community',
                 hook='community',caption='community',community=community,region=region)
    ranked=[trend_rank(t,sample) for t in newest.values()]
    return sorted(ranked,key=lambda x:x['score'],reverse=True)[:limit]

def hashtag_suggestions(draft, trends):
    newest={}
    for t in trends:
        if t.platform!=draft.platform or t.region.upper()!=draft.region.upper():continue
        if t.hashtag not in newest or t.observed_at>newest[t.hashtag].observed_at:newest[t.hashtag]=t
    ranked=sorted([trend_rank(t,draft) for t in newest.values()],key=lambda t:t['score'],reverse=True)
    selected=[]
    for item in ranked:
        # Avoid sending unrelated viral tags to the user.
        if item['relevance']>=.25 and item['freshness']>=.2 and item['hashtag'] not in draft.hashtags:
            selected.append(item)
        if len(selected)==5:break
    return {'recommended':selected, 'already_used':draft.hashtags,
            'trends_loaded':len(newest),
            'message':'Trend-backed recommendations' if selected else
                      'No sufficiently relevant, recent trends in connected data; avoid pretending a hashtag is trending.'}

def stable_features(caption,hook,duration):
    hook=hook or caption[:90]
    words=caption.split()
    first=hook.strip()
    return [
        clamp(len(first)/90),
        1.0 if '?' in first else 0.0,
        1.0 if re.search(r'\b(how|why|watch|before|mistake|secret|stop|try|proof|pov)\b',first,re.I) else 0.,
        clamp(len(words)/120),
        clamp(len(re.findall(r'#[\w]+',caption))/8),
        1.0 if re.search(r'\b(you|your)\b',first,re.I) else 0.,
        1.0 if 7<=duration<=45 else .45 if duration<=90 else .15,
        1.0 if re.search(r'\b(save|share|comment|follow|learn|shop|download|sign up|link)\b',caption,re.I) else 0.
    ]

def train_reach(posts):
    """Estimate chance to beat *this creator's* historical 75th percentile.

    No claim this reveals platform ranking internals. Avoid leakage by using only
    observable PRE-publication text, not likes/views as predictors.
    """
    useful=[p for p in posts if p.views>0]
    if len(useful)<35:return None,{'trained':False,'reason':'Need at least 35 posts with views on this platform.'}
    baseline=np.percentile([p.views for p in useful],75)
    labels=[int(p.views>=baseline) for p in useful]
    if min(Counter(labels).values())<6 or len(set(labels))<2:
        return None,{'trained':False,'reason':'Not enough examples in both reach classes.'}
    x=[stable_features(p.caption,p.hook,p.duration_seconds) for p in useful]
    model=make_pipeline(StandardScaler(), LogisticRegression(max_iter=500,random_state=7))
    model.fit(x,labels)
    return model,{'trained':True,'samples':len(useful),'target':f'Exceed own historical 75th percentile ({baseline:.0f} views)',
                  'note':'In-sample fitted estimate; validate on future posts. Not an algorithm leak or guaranteed viral probability.'}

def reach_analysis(draft:Draft,posts,all_trends):
    suggestions=hashtag_suggestions(draft,all_trends)
    trend_fit=clamp(max((v['score'] for v in suggestions['recommended']),default=0)/100)
    feat=stable_features(draft.caption,draft.hook,draft.duration_seconds)
    hook_quality=clamp((feat[0]*.35+feat[1]*.20+feat[2]*.25+feat[5]*.20))
    caption_quality=clamp(.6*(1-abs(len(draft.caption.split())-55)/160)+.4*min(len(terms(draft.topic+' '+draft.caption))/20,1))
    is_short=draft.platform=='youtube'
    style_fit=float(draft.duration_seconds<=180) if is_short else feat[6]
    novelty=1.0-max((similarity(draft.caption,p.caption) for p in posts if p.caption),default=0)
    hashtag_fit=clamp((len(draft.hashtags)+len(suggestions['recommended']))/5)
    score=100*(.30*hook_quality+.19*caption_quality+.15*style_fit+.15*trend_fit+.13*novelty+.08*hashtag_fit)
    trained,training=train_reach(posts)
    result={'reach_readiness_score':round(score,1),'score_type':'editorial readiness heuristic, NOT probability of virality',
      'signals':{'hook_strength':round(hook_quality*100,1),'caption_clarity':round(caption_quality*100,1),
                 'format_fit':round(style_fit*100,1),'trending_topic_fit':round(trend_fit*100,1),
                 'novelty_vs_your_posts':round(novelty*100,1),'hashtag_relevance_coverage':round(hashtag_fit*100,1)},
      'hashtags':suggestions,'training':training,'estimated_top_quartile_probability':None,'recommendations':[]}
    if trained:
        result['estimated_top_quartile_probability']=round(float(trained.predict_proba([feat])[0,1]),3)
    rec=[]
    if hook_quality<.65:rec.append('Rewrite the first 1–3 seconds as a specific curiosity gap, proof, or audience problem.')
    if novelty<.45:rec.append('Differentiate this concept from your previous captions and angles.')
    if trend_fit<.35:rec.append('No strong niche-relevant trend signal yet. Verify a fresh regional trend feed before borrowing a format.')
    if not draft.hashtags and not suggestions['recommended']:rec.append('Add 2–5 precise topic/community hashtags, not generic #fyp spam.')
    if is_short:
        rec.append('Plan a vertical or square frame and use a specific title that matches the opening. Show the result early, then cut straight to how it happens.')
        if draft.duration_seconds>180:
            rec.append('Trim the draft to 180 seconds or less for YouTube Shorts.')
    elif draft.duration_seconds>70:rec.append('Consider a tighter edit with an early payoff; compare retention from past posts before shortening automatically.')
    if not rec:rec.append('Test two distinct hooks on future comparable posts, then measure early retention and reach.')
    result['recommendations']=rec
    return result

def conversion_analysis(draft:Draft, campaign_stats=None):
    """Separate post-click funnel model. Optimize qualified outcomes, not views."""
    cta=draft.call_to_action.lower()
    offer=draft.offer.lower()
    action=bool(re.search(r'\b(shop|buy|book|join|download|start|apply|subscribe|register|reserve|visit|click|dm)\b',cta))
    value=bool(re.search(r'\b(free|save|learn|guide|template|trial|off|bonus|early|exclusive|step|plan)\b',offer+' '+cta))
    relevance=similarity(draft.offer+' '+draft.call_to_action,draft.topic+' '+draft.caption)
    has_page=draft.landing_page is not None
    cta_score=100*(.29*action+.25*bool(offer)+.21*has_page+.12*value+.13*clamp(relevance*3))
    recommendations=[]
    if not action:recommendations.append('Use one explicit action verb in the CTA, e.g., “Book a call” or “Get the guide”.')
    if not offer:recommendations.append('Describe the concrete benefit and why this audience should care.')
    if not has_page:recommendations.append('Add a conversion destination with consistent offer messaging and UTM tracking.')
    if not value:recommendations.append('Give a reason to act now without fabricated scarcity or false urgency.')
    evidence={'clicks':0,'conversions':0,'revenue':0,'conversion_rate':None,'data_status':'No observed campaign funnel data'}
    if campaign_stats:
        clicks=sum(x.get('clicks',0) for x in campaign_stats)
        conversions=sum(x.get('conversions',0) for x in campaign_stats)
        revenue=sum(x.get('revenue',0) for x in campaign_stats)
        evidence={'clicks':clicks,'conversions':conversions,'revenue':round(revenue,2),
                  'conversion_rate':round(conversions/clicks,4) if clicks else None,
                  'data_status':'Observed funnel results' if clicks else 'No clicks tracked'}
    return {'conversion_readiness_score':round(cta_score,1),
      'score_type':'funnel readiness heuristic, not predicted sales',
      'cta_action_present':action,'destination_present':has_page,
      'observed_funnel':evidence,'recommendations':recommendations}

def choose_variants(stats, value_per_conversion=0):
    """Independent conversion bandit: Beta-smoothed CTR and CVR.

    Posterior means are conservative and favor data quality. Explore when
    small sample size is uncertain; not a causal lift claim.
    """
    result=[]
    for row in stats:
        views=row['views'];clicks=row['clicks'];convs=row['conversions']
        valid_views=max(views,clicks) # Redirect traffic may exist without registered exposure.
        # CTR prior ~1%; CVR prior ~5%. Strong priors are not factual forecasts.
        ctr=(1+clicks)/(100+valid_views)
        attributable=min(convs,clicks) # A conversion without a tracked click is not provably link-attributed.
        cvr=(1+attributable)/(20+clicks)
        per_1k=1000*ctr*cvr if views>0 else None
        result.append({**row, 'smoothed_ctr':round(ctr,4) if views else None,
            'smoothed_cvr':round(cvr,4) if clicks else None,
            'expected_conversions_per_1000_views':round(per_1k,3) if per_1k is not None else None,
            'expected_revenue_per_1000_views':round(per_1k*value_per_conversion,2) if per_1k is not None else None,
            'tracking_quality':'missing_exposure' if views==0 else 'unattributed_conversions' if convs>clicks else 'has_exposure',
            'data_note':'Bayesian-smoothed point estimate, not guaranteed future performance.'})
    return sorted(result,key=lambda r: r['expected_conversions_per_1000_views'] if r['expected_conversions_per_1000_views'] is not None else -1,reverse=True)

def orchestrate(draft, store):
    posts=store.posts(draft.platform)
    trends=store.trends(draft.platform,draft.region)
    reach=reach_analysis(draft,posts,trends)
    conversion=conversion_analysis(draft)
    return {'post':{'platform':draft.platform,'topic':draft.topic,'goal':draft.goal},
      'reach_model':reach,'conversion_model':conversion,
      'optimization_priority':('Improve conversion offer and destination first' if draft.goal!='reach' and conversion['conversion_readiness_score']<65
            else 'Improve creative hook and trend fit' if reach['reach_readiness_score']<65 else 'Publish a controlled test and measure outcomes'),
      'data_quality':{'connected_post_count':len(posts),'trend_observation_count':len(trends),
          'fresh_trend_count':len([t for t in trends if (datetime.now(timezone.utc)- (t.observed_at.replace(tzinfo=timezone.utc) if t.observed_at.tzinfo is None else t.observed_at)).total_seconds()<=86400]),
          'cannot_guarantee_virality':True}}

def momentum_opportunities(snapshots:list[Snapshot], campaign_stats:dict|None=None):
    """Detect an unusually strong *observed* growth window, not future virality.

    A first snapshot isn't a trend; require >=2 observations and baseline of
    several posts. No action is auto-published or triggered on behalf of a user.
    """
    groups={}
    for item in snapshots:
        groups.setdefault(item.post_id,[]).append(item)
    measured=[]
    for post_id,items in groups.items():
        items.sort(key=lambda s:s.observed_at)
        if len(items)<2:continue
        old,new=items[-2:]
        start=old.observed_at.replace(tzinfo=timezone.utc) if old.observed_at.tzinfo is None else old.observed_at
        end=new.observed_at.replace(tzinfo=timezone.utc) if new.observed_at.tzinfo is None else new.observed_at
        hrs=(end-start).total_seconds()/3600
        if hrs<.05:continue # <3 min gaps are too noisy
        velocity=max(0,new.views-old.views)/hrs
        measured.append({'post_id':post_id,'views':new.views,'velocity_views_per_hour':round(velocity,1),
                         'shares_per_view':round(new.shares/max(1,new.views),4),
                         'hours_between_observations':round(hrs,2),
                         'campaign_id':new.campaign_id,'variant_id':new.variant_id})
    baseline=median([r['velocity_views_per_hour'] for r in measured]) if measured else 0
    for item in measured:
        ratio=item['velocity_views_per_hour']/baseline if baseline>0 and len(measured)>=3 else None
        item['velocity_vs_creator_median']=round(ratio,2) if ratio is not None else None
        gaining=ratio is not None and ratio>=2 and item['views']>=100
        item['status']='takeoff_candidate' if gaining else 'observing'
        item['opportunity_score']=round(100*clamp(
             .65*min(ratio/3,1)+.35*min(item['shares_per_view']/.025,1))) if ratio is not None else None
        campaign_key=(item['campaign_id'],item['variant_id'])
        funnel=(campaign_stats or {}).get(campaign_key)
        if gaining and funnel and funnel.get('views',0)>=100 and funnel.get('clicks',0)/max(1,funnel['views'])<.01:
            action='Content is spreading faster than usual but tracked click-through is weak. Test one clearer offer and CTA on your owned destination.'
        elif gaining and item['shares_per_view']>.02:
            action='High growth and shares: make a timely follow-up using the same topic, with a new valuable angle and a clearly relevant CTA.'
        elif gaining:
            action='A takeoff candidate: prepare a useful follow-up, respond to genuine comments, and inspect tracked funnel results.'
        else:
            action='Keep measuring on a consistent schedule; no robust takeoff signal detected.'
        item['recommended_next_action']=action
    return {'posts_compared':len(measured),'median_velocity_views_per_hour':round(baseline,1),
            'data_requirement':'At least 2 snapshots per post, 3 posts for relative takeoff detection; snapshots >=3 minutes apart.',
            'opportunities':sorted(measured,key=lambda r:(r['opportunity_score'] is not None,r['opportunity_score'] or 0),reverse=True)}


def algorithm_audit(posts:list[Observation]):
    """Observational black-box factor audit over creator-owned posts.

    Only pre-post observable features (text/duration) enter this comparison.
    Cohorts can be confounded by subject, timing, paid views, and post age.
    """
    useful=[p for p in posts if p.views>0]
    if len(useful)<15:
        return {'ready':False,'samples':len(useful),
                'required':'15 posts with nonzero observed views for exploratory cohort comparisons.',
                'warning':'No access to proprietary recommendation weights.'}
    def features(p):
        tags=len(re.findall(r'#[\w]+',p.caption))
        count=len(p.caption.split())
        return {'question_in_hook': '?' in (p.hook or p.caption[:90]),
                '2_to_5_hashtags':2<=tags<=5,
                'short_video_7_to_45s':7<=p.duration_seconds<=45,
                'caption_10_to_100_words':10<=count<=100}
    factors=[]
    for name in features(useful[0]):
        yes=[p.views for p in useful if features(p)[name]]
        no=[p.views for p in useful if not features(p)[name]]
        if min(len(yes),len(no))<5:continue
        med_yes=median(yes);med_no=median(no)
        lift=med_yes/max(med_no,1)-1
        factors.append({'feature':name,'with_feature_posts':len(yes),
          'without_feature_posts':len(no),'median_views_with_feature':med_yes,
          'median_views_without_feature':med_no,'observed_median_lift_pct':round(100*lift,1),
          'evidence_strength':'exploratory' if min(len(yes),len(no))<15 else 'larger_observational_sample'})
    return {'ready':True,'samples':len(useful),
            'factors':sorted(factors,key=lambda f:f['observed_median_lift_pct'],reverse=True),
            'warning':'This is an observational comparison, NOT causal inference, a feed algorithm decode, or a forecast. Match post age/organic reach and test experimentally.'}

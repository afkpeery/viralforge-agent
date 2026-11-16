from __future__ import annotations
import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
import httpx
from fastapi import FastAPI, Header, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Annotated
from .models import Draft, Trend, Observation, Campaign, ConversionEvent, Exposure, Snapshot
from .storage import Store
from .engine import orchestrate, top_trends, choose_variants, momentum_opportunities, algorithm_audit
from . import connectors
from .link_analysis import LinkSubmission, LinkError, inspect_public_link

class Settings(BaseSettings):
    model_config=SettingsConfigDict(env_file='.env', extra='ignore')
    agent_api_key:str=''
    token_encryption_key:str=''
    database_path:str='./viralforge.db'
    tiktok_client_key:str=''
    tiktok_client_secret:str=''
    tiktok_redirect_uri:str=''
    instagram_app_id:str=''
    instagram_app_secret:str=''
    instagram_redirect_uri:str=''
    instagram_graph_version:str='v24.0'
    trend_feed_url:str=''
    trend_feed_bearer_token:str=''
    allowed_origins:str='http://127.0.0.1:8000,http://localhost:8000'

settings=Settings()
store=Store(settings.database_path)
app=FastAPI(title='ViralForge Social Intelligence Agent',version='0.1.0',
 description='Consent-based creator analytics and independent reach/conversion optimization. No viral guarantees.')
app.add_middleware(CORSMiddleware,allow_origins=settings.allowed_origins.split(','),
                   allow_methods=['GET','POST'], allow_headers=['X-Agent-Key','Content-Type'])

async def authorize(x_agent_key: Annotated[str|None, Header()]=None):
    if not settings.agent_api_key or not x_agent_key or not secrets.compare_digest(x_agent_key,settings.agent_api_key):
        raise HTTPException(status_code=401,detail='Valid X-Agent-Key required; configure AGENT_API_KEY')

Auth=Depends(authorize)

def require_crypto():
    if not settings.token_encryption_key:
        raise HTTPException(503,'Set TOKEN_ENCRYPTION_KEY in .env before connecting accounts.')

def require_provider(platform):
    if platform=='tiktok':
        valid=all([settings.tiktok_client_key,settings.tiktok_client_secret,settings.tiktok_redirect_uri])
    elif platform=='instagram':
        valid=all([settings.instagram_app_id,settings.instagram_app_secret,settings.instagram_redirect_uri])
    else:raise HTTPException(404,'Unknown provider')
    if not valid:raise HTTPException(503,f'Configure {platform} OAuth credentials and callback URI in .env')
    require_crypto()

@app.get('/',include_in_schema=False)
def home():
    return FileResponse(Path(__file__).resolve().parent.parent/'web'/'index.html')

@app.get('/health')
def health():
    return {'ok':True,'agent':'ViralForge','live_trends_require_import_or_licensed_feed':True}

@app.get('/api/accounts',dependencies=[Auth])
def accounts():
    require_crypto()
    return {platform: {'connected':store.get_token(platform,settings.token_encryption_key) is not None}
            for platform in ('tiktok','instagram')}

@app.post('/api/auth/{platform}/start',dependencies=[Auth])
def auth_start(platform:str):
    require_provider(platform)
    state=secrets.token_urlsafe(36)
    store.add_state(state,platform)
    if platform=='tiktok':
        url='https://www.tiktok.com/v2/auth/authorize/?'+urlencode({
            'client_key':settings.tiktok_client_key,'response_type':'code',
            'scope':'user.info.basic,video.list','redirect_uri':settings.tiktok_redirect_uri,'state':state})
    else:
        url='https://www.instagram.com/oauth/authorize?'+urlencode({
            'client_id':settings.instagram_app_id,'redirect_uri':settings.instagram_redirect_uri,
            'scope':'instagram_business_basic,instagram_business_manage_insights',
            'response_type':'code','state':state})
    return {'authorization_url':url,'expires_in_seconds':600,
            'note':'Open URL in browser, approve access, and return through registered HTTPS callback.'}

@app.get('/auth/{platform}/callback',include_in_schema=False)
async def oauth_callback(platform:str, code:str='',state:str='',error:str=''):
    require_provider(platform)
    if error:
        raise HTTPException(400,'Authorization denied by provider.')
    if not code or not state or not store.consume_state(state,platform):
        raise HTTPException(400,'Authorization state invalid, missing, expired, or already used.')
    try:
        if platform=='tiktok':
            token=await connectors.tiktok_exchange(code,settings.tiktok_client_key,settings.tiktok_client_secret,settings.tiktok_redirect_uri)
        else:
            token=await connectors.instagram_exchange(code,settings.instagram_app_id,settings.instagram_app_secret,settings.instagram_redirect_uri)
        store.put_token(platform,token,settings.token_encryption_key)
    except connectors.ProviderError as exc:
        raise HTTPException(502,'Provider token exchange failed; check app settings, callback URL, and granted scopes.') from exc
    return HTMLResponse('<html><body style="background:#0b1020;color:white;font:20px sans-serif;padding:45px">Account connected. You can return to ViralForge and sync your data.</body></html>')

@app.post('/api/accounts/{platform}/sync',dependencies=[Auth])
async def sync(platform:str):
    require_provider(platform)
    token=store.get_token(platform,settings.token_encryption_key)
    if not token:raise HTTPException(404,f'Connect {platform} account first')
    try:
        if platform=='tiktok':
            if token.get('expires_at',0)<time.time()+900:
                token=await connectors.tiktok_refresh(token,settings.tiktok_client_key,settings.tiktok_client_secret)
                store.put_token(platform,token,settings.token_encryption_key)
            posts=await connectors.tiktok_posts(token)
        else:
            if token.get('expires_at',0)<time.time()+5*86400:
                token=await connectors.instagram_refresh(token)
                store.put_token(platform,token,settings.token_encryption_key)
            posts=await connectors.instagram_posts(token,settings.instagram_graph_version)
    except connectors.ProviderError as exc:
        raise HTTPException(502,f'{platform} sync failed. Check scopes, token expiry and provider response.') from exc
    for post in posts:
        store.put_post(post)
        if post.views>0:
            store.put_snapshots([Snapshot(platform=post.platform,post_id=post.post_id,views=post.views,
                likes=post.likes,comments=post.comments,shares=post.shares)])
    return {'platform':platform,'synced':len(posts),'stored_total':len(store.posts(platform)),
            'note':'Platform-owned posts only. Some media metrics may be unavailable by permission or format.'}

@app.post('/api/posts/import',dependencies=[Auth])
def import_posts(posts:list[Observation]):
    for post in posts:
        store.put_post(post)
        if post.views>0:
            store.put_snapshots([Snapshot(platform=post.platform,post_id=post.post_id,views=post.views,
                likes=post.likes,comments=post.comments,shares=post.shares)])
    return {'stored':len(posts)}

@app.get('/api/posts/{platform}',dependencies=[Auth])
def list_posts(platform:str):
    if platform not in ('instagram','tiktok'):raise HTTPException(404,'Unknown platform')
    return store.posts(platform)

@app.post('/api/snapshots/import',dependencies=[Auth])
def import_snapshots(items:list[Snapshot]):
    store.put_snapshots(items)
    return {'stored':len(items)}

@app.get('/api/momentum/{platform}',dependencies=[Auth])
def momentum(platform:str):
    if platform not in ('tiktok','instagram'):raise HTTPException(404,'Unknown platform')
    return momentum_opportunities(store.snapshots(platform))

@app.get('/api/algorithm-audit/{platform}',dependencies=[Auth])
def audit(platform:str):
    if platform not in ('instagram','tiktok'):raise HTTPException(404,'Unknown platform')
    return algorithm_audit(store.posts(platform))

@app.post('/api/trends/import',dependencies=[Auth])
def import_trends(items:list[Trend]):
    store.put_trends(items)
    return {'stored':len(items),'message':'Imported observations are only current as of observed_at.'}

@app.post('/api/trends/refresh',dependencies=[Auth])
async def refresh_trends():
    """Only a configured, licensed JSON provider is contacted; never arbitrary URLs or scrapers."""
    if not settings.trend_feed_url or not settings.trend_feed_url.startswith('https://'):
        raise HTTPException(503,'Configure an approved HTTPS TREND_FEED_URL, or import current data manually.')
    headers={'Accept':'application/json'}
    if settings.trend_feed_bearer_token:
        headers['Authorization']='Bearer '+settings.trend_feed_bearer_token
    try:
        async with httpx.AsyncClient(follow_redirects=False,timeout=20) as client:
            r=await client.get(settings.trend_feed_url,headers=headers)
            r.raise_for_status()
            data=r.json()
        items=[Trend.model_validate(item) for item in (data['trends'] if isinstance(data,dict) else data)]
        store.put_trends(items)
        return {'imported':len(items),'source_url_configured':True}
    except Exception as exc:
        raise HTTPException(502,'Trend provider request failed; verify provider response against Trend schema.') from exc

@app.get('/api/trends/{platform}',dependencies=[Auth])
def trends(platform:str, region:str='US',niche:str='',community:str='',limit:int=Query(15,ge=1,le=100)):
    if platform not in ('instagram','tiktok'):raise HTTPException(404,'Unknown platform')
    ranked=top_trends(store.trends(platform,region),platform,region,niche,community,limit)
    return {'trends':ranked,'fresh_count':sum(t['live'] for t in ranked),
            'notice':'No independent platform-wide trend access is implied; sources and timestamps are shown.'}

@app.post('/api/link/analyze',dependencies=[Auth])
async def analyze_public_link(submission: LinkSubmission):
    """Inspect an allowed public post URL through official oEmbed endpoints."""
    try:
        return await inspect_public_link(submission.url)
    except LinkError as exc:
        raise HTTPException(422,detail=str(exc)) from exc

@app.get('/data/trend_news.json',include_in_schema=False)
def news_snapshot():
    from fastapi.responses import JSONResponse
    path=Path(__file__).resolve().parent.parent/'data'/'trend_news.json'
    if not path.is_file():
        return JSONResponse({'generated_at':None,'feeds':{}})
    return FileResponse(path,media_type='application/json')

@app.post('/api/analyze',dependencies=[Auth])
def analyze(draft:Draft):
    return orchestrate(draft,store)

@app.post('/api/campaigns',dependencies=[Auth])
def create_campaign(c:Campaign):
    store.put_campaign(c)
    return {'campaign_id':c.campaign_id,'variant_id':c.variant_id,
        'tracking_path':f'/go/{c.campaign_id}/{c.variant_id}',
        'note':'Use public HTTPS deployment for clickable tracking links; do not expose this API without authentication and rate limiting.'}

@app.get('/go/{campaign_id}/{variant_id}',include_in_schema=False)
def click_redirect(campaign_id:str,variant_id:str):
    row=store.campaign(campaign_id,variant_id)
    if not row:raise HTTPException(404,'Unknown campaign link')
    destination=urlsplit(row['destination'])
    query=dict(parse_qsl(destination.query,keep_blank_values=True))
    query.update({'utm_source':row['platform'],'utm_medium':'organic_social',
                  'utm_campaign':campaign_id,'utm_content':variant_id})
    store.record_click(campaign_id,variant_id)
    return RedirectResponse(urlunsplit((destination.scheme,destination.netloc,destination.path,
                                     urlencode(query),destination.fragment)),status_code=302)

@app.post('/api/campaigns/exposure',dependencies=[Auth])
def set_exposure(item:Exposure):
    if not store.campaign(item.campaign_id,item.variant_id):raise HTTPException(404,'Unknown campaign variant')
    store.set_exposure(item.campaign_id,item.variant_id,item.views)
    return {'recorded':True,'note':'Views are cumulative, not increments.'}

@app.post('/api/events/conversion',dependencies=[Auth])
def record_conversion(event:ConversionEvent):
    if not store.campaign(event.campaign_id,event.variant_id):raise HTTPException(404,'Unknown campaign variant')
    created=store.record_conversion(event)
    return {'recorded':created,'duplicate':not created}

@app.get('/api/campaigns/{campaign_id}/optimize',dependencies=[Auth])
def optimize_campaign(campaign_id:str,conversion_value:float=Query(0,ge=0)):
    rows=store.campaign_stats(campaign_id)
    if not rows:raise HTTPException(404,'Unknown campaign')
    return {'campaign_id':campaign_id,'objective':'expected conversions per 1000 observed views',
            'variants':choose_variants(rows,conversion_value),
            'caution':'Small-sample posterior estimates do not prove causation. Rotate variants and measure consistently.'}

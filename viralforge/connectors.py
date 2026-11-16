"""Only official, user-consented APIs. Never scraper/session-cookie automation."""
from __future__ import annotations
import time
from datetime import datetime, timezone
import httpx
from .models import Observation

class ProviderError(Exception):
    pass

async def fetch(client, method, url, **kwargs):
    try:
        response = await client.request(method, url, timeout=25, **kwargs)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and isinstance(data.get('error'),dict):
            err=data['error']
            if err.get('code') not in (None,0,'ok','OK'):
                raise ProviderError(f'Platform error: {err}')
        elif isinstance(data,dict) and data.get('error'):
            raise ProviderError(f'Platform error: {data["error"]}')
        return data
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise ProviderError(f'Platform request failed: {str(exc)[:300]}') from exc

async def tiktok_exchange(code, client_key, client_secret, redirect_uri):
    async with httpx.AsyncClient() as client:
        result = await fetch(client,'POST','https://open.tiktokapis.com/v2/oauth/token/', data={
          'client_key':client_key,'client_secret':client_secret,'code':code,
          'grant_type':'authorization_code','redirect_uri':redirect_uri})
    if 'access_token' not in result: raise ProviderError(f'TikTok token exchange failed: {result}')
    result['expires_at'] = time.time() + int(result.get('expires_in',0))
    return result

async def tiktok_refresh(token, client_key, client_secret):
    async with httpx.AsyncClient() as client:
        result=await fetch(client,'POST','https://open.tiktokapis.com/v2/oauth/token/', data={
          'client_key':client_key,'client_secret':client_secret,
          'grant_type':'refresh_token','refresh_token':token['refresh_token']})
    if 'access_token' not in result: raise ProviderError(f'TikTok refresh failed: {result}')
    result['expires_at']=time.time()+int(result.get('expires_in',0))
    return result

async def tiktok_posts(token, pages=3):
    output=[]; cursor=None
    async with httpx.AsyncClient() as client:
        for _ in range(pages):
            body={'max_count':20}
            if cursor: body['cursor']=cursor
            resp=await fetch(client,'POST','https://open.tiktokapis.com/v2/video/list/',
                params={'fields':'id,create_time,video_description,title,duration,view_count,like_count,comment_count,share_count'},
                headers={'Authorization':'Bearer '+token['access_token']},json=body)
            data=resp.get('data',{})
            for video in data.get('videos',[]):
                output.append(Observation(platform='tiktok',post_id=str(video['id']),
                  caption=video.get('video_description') or video.get('title') or '',
                  views=video.get('view_count') or 0,likes=video.get('like_count') or 0,
                  comments=video.get('comment_count') or 0,shares=video.get('share_count') or 0,
                  duration_seconds=video.get('duration') or 25,
                  created_at=datetime.fromtimestamp(video.get('create_time',time.time()),tz=timezone.utc)))
            if not data.get('has_more'):break
            cursor=data.get('cursor')
            if not cursor:break
    return output

async def instagram_exchange(code, app_id, app_secret, redirect_uri):
    async with httpx.AsyncClient() as client:
        short=await fetch(client,'POST','https://api.instagram.com/oauth/access_token', data={
          'client_id':app_id,'client_secret':app_secret,'grant_type':'authorization_code',
          'redirect_uri':redirect_uri,'code':code})
        long=await fetch(client,'GET','https://graph.instagram.com/access_token',params={
          'grant_type':'ig_exchange_token','client_secret':app_secret,'access_token':short['access_token']})
    long['user_id']=str(short.get('user_id',''))
    long['expires_at']=time.time()+int(long.get('expires_in',0))
    return long

async def instagram_refresh(token):
    async with httpx.AsyncClient() as client:
        new=await fetch(client,'GET','https://graph.instagram.com/refresh_access_token',params={
          'grant_type':'ig_refresh_token','access_token':token['access_token']})
    new['user_id']=token['user_id']
    new['expires_at']=time.time()+int(new.get('expires_in',0))
    return new

async def instagram_posts(token, version='v24.0', pages=3):
    # Insights and individual metrics differ by account/media type; keep unavailable fields null/0.
    base=f'https://graph.instagram.com/{version}'
    output=[]
    async with httpx.AsyncClient() as client:
        url=f'{base}/me/media'; params={'fields':'id,caption,media_type,timestamp,like_count,comments_count,permalink',
                                       'limit':30,'access_token':token['access_token']}
        for _ in range(pages):
            resp=await fetch(client,'GET',url,params=params)
            for media in resp.get('data',[]):
                views=0; saves=0; shares=0
                try:
                    insight=await fetch(client,'GET',f'{base}/{media["id"]}/insights',params={
                        'metric':'views,reach,saved,shares','access_token':token['access_token']})
                    values={x['name']:x.get('values',[{}])[0].get('value',x.get('total_value',{}).get('value',0))
                            for x in insight.get('data',[])}
                    views=int(values.get('views') or values.get('reach') or 0)
                    saves=int(values.get('saved') or 0); shares=int(values.get('shares') or 0)
                except ProviderError:
                    # Some media types reject the multi-metric request. Try individual
                    # view/reach metrics; never fabricate missing values.
                    for metric in ('views','reach'):
                        try:
                            single=await fetch(client,'GET',f'{base}/{media["id"]}/insights',params={
                                'metric':metric,'access_token':token['access_token']})
                            for entry in single.get('data',[]):
                                raw=entry.get('values',[{}])[0].get('value',entry.get('total_value',{}).get('value',0))
                                views=int(raw or 0)
                            if views:break
                        except ProviderError:
                            continue
                output.append(Observation(platform='instagram',post_id=str(media['id']),
                    caption=media.get('caption') or '',views=views,
                    likes=media.get('like_count') or 0,comments=media.get('comments_count') or 0,
                    shares=shares,saves=saves,
                    created_at=datetime.fromisoformat(media['timestamp'].replace('Z','+00:00'))))
            next_url=resp.get('paging',{}).get('next')
            if not next_url:break
            # Provider-supplied pagination URL; restrict host and HTTPS to avoid SSRF.
            from urllib.parse import urlparse
            parsed=urlparse(next_url)
            if parsed.scheme != 'https' or parsed.netloc != 'graph.instagram.com':break
            url=next_url;params=None
    return output

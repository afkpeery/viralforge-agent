"""Authorized public embed metadata only; no unauthorized scraping or private social metrics."""
from __future__ import annotations
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs,urlsplit,urlunsplit
import httpx
from pydantic import BaseModel,Field

class LinkSubmission(BaseModel):
    url:str=Field(min_length=12,max_length=2048)

class LinkError(ValueError):
    pass

HOSTS={
'tiktok.com':'tiktok','www.tiktok.com':'tiktok','m.tiktok.com':'tiktok','vm.tiktok.com':'tiktok','vt.tiktok.com':'tiktok',
'instagram.com':'instagram','www.instagram.com':'instagram',
'x.com':'x','www.x.com':'x','twitter.com':'x','www.twitter.com':'x','mobile.twitter.com':'x',
'facebook.com':'facebook','www.facebook.com':'facebook','m.facebook.com':'facebook','fb.watch':'facebook','www.fb.watch':'facebook',
'youtube.com':'youtube','www.youtube.com':'youtube','m.youtube.com':'youtube','youtu.be':'youtube'}

class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.suppressed=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.suppressed+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.suppressed:self.suppressed-=1
    def handle_data(self,data):
        if not self.suppressed:self.parts.append(data)

def plain_html(source):
    parser=_PlainText();parser.feed(source)
    return re.sub(r'\s+',' ',' '.join(parser.parts)).strip()[:1000]

def classify_url(raw: str)->dict:
    raw=raw.strip()
    try:
        parts=urlsplit(raw);host=(parts.hostname or '').lower()
        if parts.scheme!='https' or parts.username or parts.password or parts.port not in (None,443) or any(c.isspace() for c in raw):
            raise LinkError('Use a public HTTPS post URL without credentials or custom ports.')
    except ValueError as exc:
        raise LinkError('Please paste a valid HTTPS post URL.') from exc
    platform=HOSTS.get(host)
    if not platform:raise LinkError('Only TikTok, Instagram, X, Facebook and YouTube are supported.')
    path=parts.path.rstrip('/');query=parse_qs(parts.query);post_id=''
    if platform=='youtube':
        if host=='youtu.be':post_id=path.lstrip('/')
        elif path=='/watch':post_id=query.get('v',[''])[0]
        else:
            match=re.fullmatch(r'/(?:shorts|live|embed)/([\w-]{11})',path)
            if match:post_id=match.group(1)
        if not re.fullmatch(r'[\w-]{11}',post_id):raise LinkError('Provide a YouTube video or Shorts URL.')
    elif platform=='tiktok':
        match=re.search(r'/video/(\d{8,25})$',path)
        if match:post_id=match.group(1)
        elif re.fullmatch(r'/t/[\w-]+',path):post_id=path.split('/')[-1]
        elif host in ('vm.tiktok.com','vt.tiktok.com') and re.fullmatch(r'/[\w-]+',path):post_id=path[1:]
        else:raise LinkError('Provide a TikTok video or official short link.')
    elif platform=='instagram':
        match=re.fullmatch(r'/(?:p|reel|reels|tv)/([\w-]+)',path)
        if not match:raise LinkError('Provide an Instagram Reel or post URL.')
        post_id=match.group(1)
    elif platform=='x':
        match=re.fullmatch(r'/(?:[^/]+|i/web)/status/(\d+)',path)
        if not match:raise LinkError('Provide an X post URL with /status/...')
        post_id=match.group(1)
    else:
        match=re.search(r'/(?:videos|reel|posts|share/[rvp])/([\w.-]+)',path)
        if match:post_id=match.group(1)
        elif path in ('/permalink.php','/story.php') and query.get('story_fbid'):post_id=query['story_fbid'][0]
        elif path=='/watch' and query.get('v'):post_id=query['v'][0]
        elif host in ('fb.watch','www.fb.watch') and re.fullmatch(r'/[\w-]+',path):post_id=path[1:]
        else:raise LinkError('Provide a Facebook video, Reel or post URL.')
    url=urlunsplit(('https',host,path,parts.query if (platform in ('youtube','facebook') and path in ('/watch','/permalink.php','/story.php')) else '',''))
    return {'platform':platform,'post_id':post_id,'url':url}

def _endpoint(platform,url):
    if platform=='youtube':return 'https://www.youtube.com/oembed',{'url':url,'format':'json'}
    if platform=='tiktok':return 'https://www.tiktok.com/oembed',{'url':url}
    if platform=='x':return 'https://publish.x.com/oembed',{'url':url,'omit_script':'true','hide_thread':'true'}
    if platform=='instagram':return 'https://graph.facebook.com/v27.0/instagram_oembed',{'url':url}
    return ('https://graph.facebook.com/v27.0/oembed_video' if any(x in url for x in ('/reel/','/videos/','/watch?')) else 'https://graph.facebook.com/v27.0/oembed_post',{'url':url})

def _advice(platform,title):
    if not title:return ['The platform did not expose public post text. This link is recognized, but deeper content analysis needs permissioned metrics or a transcript.',
                          'Check that the first two seconds communicate a clear benefit or curiosity hook.',
                          'Measure watch time, saves, shares and conversions with an authorized creator account.']
    words=title.split();tags=re.findall(r'#[\w]+',title)
    if len(words)<7:intro='The caption is short: experiment with a specific hook and concrete viewer benefit.'
    elif len(words)>35:intro='Front-load the strongest claim so a long caption does not obscure the hook.'
    else:intro='Test two alternate opening hooks, then compare actual retention metrics.'
    result=[intro,('Visible hashtags: '+', '.join(tags[:5])+'. Check niche relevance and current interest.' if tags else 'No hashtags were visible. Research only specific, relevant niche tags.'),
            'Compare real watch time, shares, saves, clicks and conversions before making performance claims.']
    if platform in ('youtube','tiktok','instagram','facebook'):result.append('Video pacing, imagery and audio cannot be scored from public embed text; use a permitted media or transcript integration.')
    return result

async def inspect_public_link(raw_url: str,client: httpx.AsyncClient|None=None)->dict:
    info=classify_url(raw_url);endpoint,params=_endpoint(info['platform'],info['url'])
    title='';author='';note='';own_client=client is None
    if own_client:client=httpx.AsyncClient(timeout=8,follow_redirects=False,headers={'Accept':'application/json'})
    try:
        assert client is not None
        response=await client.get(endpoint,params=params);response.raise_for_status()
        payload=response.json()
        if not isinstance(payload,dict):raise ValueError('Unexpected metadata response')
        title=str(payload.get('title') or '').strip()[:600]
        author=str(payload.get('author_name') or '').strip()[:160]
        if not title and info['platform'] in ('x','facebook'):
            # Both providers commonly wrap the actual post text in a blockquote paragraph.
            paragraph=re.search(r'<blockquote\b[^>]*>.*?<p\b[^>]*>(.*?)</p>',str(payload.get('html','')),re.I|re.S)
            if paragraph:title=plain_html(paragraph.group(1))[:600]
        if not title:note='Provider returned embed information without a readable caption.'
    except (httpx.HTTPError,ValueError,TypeError):
        note='Public embed metadata is restricted, unavailable or temporarily rate-limited.'
    finally:
        if own_client:await client.aclose()
    return {**info,'evidence_level':'public_metadata_only' if title else 'url_identification_only',
            'metadata':{'title_or_caption':title,'author':author,'source':'official_oembed' if title else 'url_only'},
            'availability_note':note or 'Public text retrieved; private insights, video frames and audience data were not.',
            'recommendations':_advice(info['platform'],title),
            'viral_probability':None,'real_time_metrics_available':False,'requires_connected_account_for_metrics':True}

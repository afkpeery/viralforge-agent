"""Refresh public, timestamped social-platform news headlines from Google News RSS."""
import argparse,json,re,urllib.parse,urllib.request,xml.etree.ElementTree as ET
from datetime import datetime,timezone,timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
FEEDS={'tiktok':'TikTok viral creators trends','instagram':'Instagram Reels trends creators','x':'X Twitter trending posts social media','facebook':'Facebook Meta creators trending','youtube':'YouTube Shorts creators trending'}
def clean(s):return re.sub(r'\s+',' ',re.sub(r'<[^>]+>','',s or '')).strip()[:220]
def parse_rss(data,platform,now):
    root=ET.fromstring(data);results=[];seen=set()
    keys={'tiktok':('tiktok',),'instagram':('instagram','reels'),'x':('twitter',' x ','x.com'),'facebook':('facebook','meta','reels'),'youtube':('youtube','shorts')}
    for item in root.findall('.//channel/item'):
        title=clean(item.findtext('title',''));url=(item.findtext('link') or '').strip();raw=item.findtext('pubDate')
        if not title or not url.startswith('https://') or not raw:continue
        try:pub=parsedate_to_datetime(raw).astimezone(timezone.utc)
        except (TypeError,ValueError,OverflowError):continue
        if pub>now+timedelta(hours=1) or pub<now-timedelta(days=4):continue
        if not any(k in ' '+title.lower()+' ' for k in keys[platform]):continue
        norm=re.sub(r'\W+','',title.lower())
        if norm in seen:continue
        seen.add(norm)
        source=clean(item.findtext('source') or '') or (title.rsplit(' - ',1)[-1] if ' - ' in title else 'Google News index')
        results.append({'headline':title,'url':url,'source':source,'published_at':pub.isoformat(),'platform':platform,'kind':'news_headline'})
        if len(results)>=8:break
    return results
def _fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'ViralForgeNewsMonitor/1.0'})
    with urllib.request.urlopen(req,timeout=14) as r:return r.read(350000)
def build_snapshot(fetch=None,now=None,previous=None):
    now=now or datetime.now(timezone.utc);fetch=fetch or _fetch;previous=previous or {};feeds={};errors={}
    for platform,query in FEEDS.items():
        fallback_query={'tiktok':'TikTok creators', 'instagram':'Instagram', 'x':'Twitter X social media', 'facebook':'Facebook Meta', 'youtube':'YouTube Shorts'}[platform]
        results=[]
        issue=None
        for terms in (query+' when:3d',fallback_query+' when:3d'):
            url='https://news.google.com/rss/search?'+urllib.parse.urlencode({'q':terms,'hl':'en-US','gl':'US','ceid':'US:en'})
            try:
                results=parse_rss(fetch(url),platform,now)
                if results:break
            except (OSError,TimeoutError,ET.ParseError,ValueError) as exc:
                issue=str(exc)[:140]
        if not results:
            results=[x for x in previous.get('feeds',{}).get(platform,[])
                     if isinstance(x,dict) and x.get('headline') and x.get('url')][:8]
            if issue:errors[platform]=issue
        feeds[platform]=results
    return {'generated_at':now.isoformat(),'feed_type':'social_platform_news_not_verified_in_app_trends','source':'Google News RSS index / publisher headlines','feeds':feeds,'errors':errors}
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='data/trend_news.json');args=parser.parse_args()
    path=Path(args.output)
    try:previous=json.loads(path.read_text())
    except (OSError,ValueError):previous={}
    result=build_snapshot(previous=previous);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print('Headlines: '+', '.join(f'{key}={len(val)}' for key,val in result['feeds'].items()))
    if result['errors']:print('Feed errors: '+', '.join(result['errors']))
if __name__=='__main__':main()

from datetime import datetime,timezone
from scripts.update_news import parse_rss,build_snapshot
SAMPLE=b'<rss><channel><item><title>YouTube Shorts creators explain new format - Example Press</title><link>https://news.google.com/rss/articles/demo</link><pubDate>Mon, 16 Nov 2026 15:00:00 GMT</pubDate><source>Example Press</source></item></channel></rss>'
def test_headlines_have_platform_and_time():
 now=datetime(2026,11,16,16,tzinfo=timezone.utc)
 assert parse_rss(SAMPLE,'youtube',now)[0]['kind']=='news_headline'
 assert not parse_rss(SAMPLE,'instagram',now)
def test_outage_keeps_previous_headlines():
 s=build_snapshot(fetch=lambda _: (_ for _ in ()).throw(OSError('offline')),
  now=datetime(2026,11,16,16,tzinfo=timezone.utc),
  previous={'feeds':{'youtube':[{'headline':'Previous','url':'https://news.google.com/'}]}})
 assert len(s['errors'])==5
 assert s['feeds']['youtube'][0]['headline']=='Previous'

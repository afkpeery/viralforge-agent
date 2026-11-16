import pytest,httpx
from viralforge.link_analysis import classify_url,inspect_public_link,LinkError,plain_html
@pytest.mark.parametrize('url,platform',[
('https://youtu.be/dQw4w9WgXcQ','youtube'),
('https://youtube.com/shorts/dQw4w9WgXcQ','youtube'),
('https://www.tiktok.com/@creator/video/7341234567890123456','tiktok'),
('https://instagram.com/reel/xyz123_a','instagram'),
('https://x.com/creator/status/1234567890123','x'),
('https://twitter.com/creator/status/1234567890123','x'),
('https://facebook.com/reel/123456789','facebook')])
def test_url(url,platform):assert classify_url(url)['platform']==platform
@pytest.mark.parametrize('url',['https://127.0.0.1/foo','http://www.youtube.com/watch?v=dQw4w9WgXcQ','https://youtube.com@evil.com/watch?v=dQw4w9WgXcQ','https://youtube.com:999/watch?v=dQw4w9WgXcQ'])
def test_bad(url):
 with pytest.raises(LinkError):classify_url(url)
@pytest.mark.asyncio
async def test_metadata_is_not_private_insight():
 def handler(req):return httpx.Response(200,json={'title':'How I made a film #filmmaking'})
 async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cl:
  response=await inspect_public_link('https://youtu.be/dQw4w9WgXcQ',cl)
 assert response['metadata']['title_or_caption'].startswith('How')
 assert response['viral_probability'] is None
 assert response['real_time_metrics_available'] is False
@pytest.mark.asyncio
async def test_no_fabricated_metrics_on_403():
 async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _:httpx.Response(403))) as cl:
  response=await inspect_public_link('https://x.com/creator/status/1234567890123',cl)
 assert response['evidence_level']=='url_identification_only'
def test_html_safety():assert 'malicious' not in plain_html('<b>Hello</b><script>malicious</script>')

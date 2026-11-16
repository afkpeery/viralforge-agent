"""Platform-specific creative improvement plans based on *observable* post text.

No claim to reverse engineer private ranking systems or inspect unavailable footage.
"""
from __future__ import annotations
import re
from pydantic import BaseModel, Field
from .link_analysis import classify_url

class CreativeBrief(BaseModel):
    url: str = Field(min_length=12,max_length=2048)
    transcript: str = Field(default='',max_length=18000)
    opening_seconds: str = Field(default='',max_length=1200)
    goal: str = Field(default='reach',pattern='^(reach|engagement|leads|sales)$')
    audience: str = Field(default='',max_length=300)

PLATFORM_RULES = {
 'tiktok': [
  ('First-second hook','Open on the strongest moment, then make the payoff clear immediately.','Compare first-2-second retention and average watch duration.'),
  ('Watch-through and rewatch','Cut setup, remove pauses, and end with a payoff that rewards finishing.','Compare completion and replay rates.'),
  ('Searchable context','Say the subject clearly on-screen and use a concise descriptive caption.','Compare search discovery and qualified engagement.')
 ],
 'instagram': [
  ('Shareable Reel premise','Make the takeaway easy to send to a friend; show the result early.','Compare shares per reach and saves per reach.'),
  ('On-screen readability','Use high-contrast captions inside mobile safe areas and clean cover text.','Compare non-follower reach and retention.'),
  ('Original creative','Use your own footage and an identifiable visual idea instead of recycled watermarked clips.','Compare eligible reach and engagement.')
 ],
 'x': [
  ('Conversation-worthy opening','State a clear point or question in the first sentence and attach a relevant clip.','Compare replies and qualified reposts per impression.'),
  ('Accessible video','Add burned-in captions and make the clip understandable with sound off.','Compare video completion and meaningful replies.'),
  ('Native context','Explain why this clip matters now without bait or misleading claims.','Compare dwell, link clicks and engagement quality.')
 ],
 'facebook': [
  ('Meaningful story arc','Establish context, show the conflict, then deliver a satisfying resolution.','Compare watch time and meaningful comments.'),
  ('Sound-off accessibility','Add legible captions and a clear opening frame.','Compare 3-second views and retention.'),
  ('Community relevance','Ask a genuine, specific question connected to the story.','Compare meaningful comments and shares.')
 ],
 'youtube': [
  ('Title and thumbnail promise','Write one specific viewer promise and make the opening fulfill it.','Compare impressions click-through rate and early retention.'),
  ('Retention structure','Remove long intros and introduce a new visual or information beat when pacing slows.','Compare audience retention curve and average view duration.'),
  ('Next-video journey','End with a relevant next step or video, not a generic engagement demand.','Compare end-screen click-through and returning viewers.')
 ]
}
def improvement_plan(platform: str,caption: str='',transcript: str='',opening_seconds: str='',goal: str='reach',audience: str='')->dict:
    if platform not in PLATFORM_RULES:raise ValueError('Unsupported platform')
    evidence='transcript_provided' if transcript.strip() else 'caption_only' if caption.strip() else 'no_content_available'
    source=(transcript or caption).strip()
    word_count=len(re.findall(r'\b\w+\b',source))
    actions=[]
    for idx,(title,action,metric) in enumerate(PLATFORM_RULES[platform],1):
        actions.append({'priority':idx,'focus':title,'suggestion':action,'validation_metric':metric,'basis':'platform-specific creative hypothesis'})
    if opening_seconds.strip():
        actions.insert(0,{'priority':0,'focus':'Opening rewrite','suggestion':'Test this opening against a version that begins with the result or strongest visual: '+opening_seconds[:130],'validation_metric':'First 3 seconds retention','basis':'creator-provided opening description'})
    elif word_count:
        actions.append({'priority':4,'focus':'Hook experiment','suggestion':'Use the strongest concrete idea from the supplied '+('transcript' if transcript else 'caption')+' as the opening, and test a question-led alternative.','validation_metric':'Early retention and qualified shares','basis':'supplied text'})
    else:
        actions.append({'priority':4,'focus':'Add evidence','suggestion':'Paste a transcript and describe the first 3 seconds for more specific edit suggestions.','validation_metric':'No performance metric available yet','basis':'missing content'})
    if goal in ('leads','sales'):
        actions.append({'priority':5,'focus':'Conversion path','suggestion':'Show the benefit before a single clear, relevant CTA; use a trackable landing-page link.','validation_metric':'Qualified clicks and conversions per 1,000 views','basis':'creator goal'})
    return {'platform':platform,'evidence_level':evidence,'goal':goal,'audience':audience,'recommendations':actions,
            'disclaimer':'These are testable editorial hypotheses, not guaranteed algorithm triggers. Actual footage, retention and private metrics have not been inspected unless separately provided.'}

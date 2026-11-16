# ViralForge — creator intelligence agent (working framework)

An explainable, **consent-based social analytics agent** with separate reach and conversion optimizers for TikTok and Instagram. Includes a responsive web dashboard, REST API, OAuth account linking, post metric ingestion, timestamped community-trend ingestion, pre-post scoring, hashtag suggestions, and campaign click/conversion tracking.

> **What it does not do:** It cannot retrieve TikTok's/Instagram's proprietary recommendation code, guarantee a viral post, read all users' feeds, or automatically discover platform-wide trends from the standard creator APIs. It **infers observable patterns** from an authorized creator's history. Live trend claims require a genuinely fresh, permitted source and are timestamped. No scraping, credential theft, fake engagement, or unofficial private APIs.

## Quick start (Python 3.11+)

```bash
python -m venv .venv
source .venv/bin/activate    # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env          # Windows: copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Put values into AGENT_API_KEY and TOKEN_ENCRYPTION_KEY in .env.
uvicorn viralforge.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 for the dashboard, or http://127.0.0.1:8000/docs for interactive API documentation. Enter `AGENT_API_KEY` in the dashboard; keep it private. No social tokens are needed to begin with manually imported historical data and trends.

## Platform connections (actual consent-required access)

**TikTok:** Create an app at https://developers.tiktok.com/ ; configure Login Kit and Display API. Get approval for `user.info.basic` and `video.list`; set `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REDIRECT_URI`. The **web** OAuth callback must be a public HTTPS URI registered exactly with TikTok. You may use an HTTPS development tunnel with a stable domain. When configured, dashboard → Connected platforms → Connect TikTok → grant access → Sync. This retrieves *your own* posts' public performance metadata using `POST /v2/video/list/`. `video.publish` (and an audit) is **not** configured; no auto-posting is performed.

**Instagram:** Create a Meta Instagram API app at https://developers.facebook.com/ and configure **Instagram API with Instagram Login**, Business Login, your professional (Business/Creator) account, valid OAuth redirect and approved `instagram_business_basic`, `instagram_business_manage_insights` permissions. Set `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI`. Instagram personal accounts aren't supported. Follow the same dashboard Connect → grant access → Sync flow. Graph API version is configurable via `INSTAGRAM_GRAPH_VERSION`. Available metrics vary by permission/media type. Inspect the Meta console and logs if a media type cannot return insights.

**Security:** OAuth CSRF `state` is one-time use (10-minute expiration); credentials are encrypted at rest using a secret Fernet key. All dashboard/API write operations require `X-Agent-Key`. OAuth callback is public but requires verified state. **This is a developer starter, not multi-user production SaaS.** Before internet deployment add user authentication, per-tenant credential isolation, CSRF protection for dashboard actions, TLS, API throttling, webhook signature verification, secret manager, backups, observability, and more complete privacy/deletion controls. Never expose `AGENT_API_KEY`, client secrets, or platform access tokens in client-side scripts. Do not publish the SQLite file.

## Analyze your pre-post creative

Use dashboard → Analyze content; or:

```bash
curl -s http://127.0.0.1:8000/api/analyze \
  -H 'X-Agent-Key: YOUR_AGENT_API_KEY' -H 'Content-Type: application/json' \
  -d '{"platform":"tiktok","niche":"filmmaking","community":"indie directors","region":"US","topic":"behind the scenes of a brand commercial","hook":"We made a store look like a movie set in one afternoon","caption":"Here is how we built a cinematic look. #filmmaking","duration_seconds":30,"hashtags":["#filmmaking"],"goal":"leads","offer":"A free brand video concept call","call_to_action":"Book a call","landing_page":"https://example.com/consult"}'
```

The output has **two separate models**:

1. `reach_model`: heuristic **reach-readiness / 100** based on hook, clarity, duration, novelty vs your previous captions, relevant trend momentum and focused hashtag coverage. With ≥35 posts and sufficient examples in both classes, a supervised logistic model adds an **exploratory chance of beating your own historical top quartile of views**. Historical text only is used as a predictor, never future views/likes. It is not calibrated for causal virality and requires forward validation.
2. `conversion_model`: independent **conversion-readiness / 100** assessing offer, specific call-to-action, value proposition and destination. Actual conversion performance comes from tracked clicks, campaign views, and server-side conversion events, *not* from reach alone.

This separation allows a post to score high for reach and low for conversion (or the reverse). Use the `optimization_priority` output to decide what to improve.

## Black-box ranking signal audit

`GET /api/algorithm-audit/tiktok` or `/api/algorithm-audit/instagram` compares median views for cohorts with versus without pre-publication features (hook question, length, hashtag count, duration), requiring 15 historical posts and at least 5 examples in each cohort. The dashboard exposes this in **Connected platforms → Black-box ranking audit**. This is an **observational proxy**, not TikTok/Instagram's hidden algorithm or evidence of cause and effect; the output contains explicit cohort sample counts. Follow up with controlled experiments and consistent post-age/organic-reach measurements.

## Community trends: genuinely time stamped

The standard Display/Instagram creator APIs **do not grant unrestricted realtime access** to every trending hashtag in every community. You can:

- Export allowed observations from [TikTok Creative Center Trends](https://ads.tiktok.com/creative/creativeCenter/trends) or an authorized analytics provider, then import them through Dashboard → Community trends.
- Configure a **licensed JSON trend feed** with `TREND_FEED_URL` (HTTPS) and optional bearer token. `POST /api/trends/refresh` pulls it server-side. The endpoint must return an array or `{ "trends": [...] }` in the format below; build a provider adapter for proprietary source schemas. Never treat feed data as current without its actual observed timestamp.

Example schema (illustrative **placeholder only**, not a verified current trend):

```json
[
  {
    "platform":"tiktok",
    "hashtag":"#filmmaking",
    "niche":"filmmaking",
    "community":"indie creators",
    "region":"US",
    "posts":10000,
    "views":2000000,
    "growth_24h":0.20,
    "observed_at":"2026-11-16T15:00:00Z",
    "source":"your authorized trend export"
  }
]
```

Import via `POST /api/trends/import` with a JSON array and `X-Agent-Key`. A trend is *recent* if observed within 24 hours; its ranking exponentially decays over time. Hashtag recommendations require topical relevance and freshness. We never auto-populate fake trending hashtags or promise generic hashtags cause virality.

## Bring historical posts without OAuth

`POST /api/posts/import` accepts an array of creator-owned `Observation` items. Required fields: `platform`, `post_id`, and `views`; optional fields include `caption`, `hook`, `duration_seconds`, `likes`, `comments`, `shares`, `saves`, `followers_at_post`, `retention_rate`, `created_at`. Use only data you're allowed to analyze. Syncing via official OAuth populates the same store.

## Conversion lab (separate optimizer)

1. `POST /api/campaigns` with `{ "campaign_id":"launch_01", "variant_id":"hook_a", "platform":"tiktok", "destination":"https://yourdomain.com/offer" }`. Create another record with same `campaign_id`, different `variant_id`, for a controlled comparison.
2. Share your public HTTPS `/go/launch_01/hook_a` link. It records a click and appends `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` to the registered HTTPS destination.
3. `POST /api/campaigns/exposure` with `{ "campaign_id":"launch_01", "variant_id":"hook_a", "views":1000 }` to set *cumulative* post views. Do this regularly after checking real platform metrics.
4. When your trusted checkout/CRM confirms a real lead or purchase, call `POST /api/events/conversion` with a **unique** `event_id`, `campaign_id`, `variant_id`, `revenue`. Duplicates are automatically ignored. Never call this from an untrusted public client with the API key.
5. `GET /api/campaigns/launch_01/optimize?conversion_value=100` ranks variants by Bayesian-smoothed estimated *conversions per 1,000 observed views*, optionally monetized with `conversion_value`. With few observations these priors dominate and estimates are uncertain; periodically test novel variants instead of blindly selecting the current winner.

Link tracking is only attribution when the conversion event carries the corresponding variant ID from the actual visitor session / checkout; add signed first-party identity, consent and trustworthy backend integrations for production. Attribution across mobile apps and links may be incomplete.

## Architecture

```text
Dashboard / FastAPI
 ├── OAuth → TikTok Display API → observed creator posts ┐
 ├── OAuth → Instagram Graph API → observed creator posts ├→ SQLite history
 ├── Licensed trend feed / manual import ───────────────┘
 ├── Reach Engine (hook, relevance, historical learning, hashtags)
 ├── Conversion Engine (offer, CTA, landing-page readiness)
 └── Conversion Lab (tracked links + views + deduplicated conversions → Bayesian variant ranking)
```

### Momentum / viral opportunity detection

Every authorized sync records a timestamped performance snapshot for posts with available views. Sync again later, or import snapshots with `POST /api/snapshots/import` in this format:

```json
[
  {"platform":"tiktok","post_id":"your-real-post-id","observed_at":"2026-11-16T17:00:00Z","views":1400,"likes":95,"shares":30},
  {"platform":"tiktok","post_id":"your-real-post-id","observed_at":"2026-11-16T19:00:00Z","views":3300,"likes":190,"shares":90}
]
```

Get ranked actions through `GET /api/momentum/tiktok` or `GET /api/momentum/instagram`, or in Conversion lab → **Scan post momentum**. The agent requires at least two snapshots at least three minutes apart and at least three measured posts for a relative takeoff alert. Results compare view velocity against the creator's median, then suggest appropriate follow-ups, community engagement, or CTA improvements. These are **observed** changes, not a prediction of future views. Real API providers do not supply synthetic time-series historical snapshots in this starter; they are accumulated only after connecting and syncing.

**Operational next steps**: implement production-grade identity/tenants, scheduled token refresh and sync, Meta/TikTok per-product scope review, permitted community-trend provider, richer optional video analysis (first-frame/transcript/audio/retention), and live dashboards. For historical modeling, capture comparable post age (e.g., 48-hour views), organic vs paid reach and retention to avoid biased comparisons. Run `pytest -q` to validate core invariants.

## Platform documentation verified in November 2026

- TikTok Display API: https://developers.tiktok.com/docs/en/display-api-overview
- TikTok Login Kit: https://developers.tiktok.com/docs/en/login-kit-web
- TikTok token endpoint: https://developers.tiktok.com/docs/en/oauth-get-a-user-access-token
- TikTok Creative Center Trends: https://ads.tiktok.com/resources/help/article/how-to-use-trends
- Instagram Platform (Instagram Login, professional accounts): https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/v21.0/
- Meta's Instagram Insights reference: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/insights

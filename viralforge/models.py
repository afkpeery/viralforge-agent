from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl, field_validator

Platform = Literal['tiktok', 'instagram']
DraftPlatform = Literal['tiktok', 'instagram', 'youtube']

class Draft(BaseModel):
    platform: DraftPlatform
    niche: str = Field(min_length=2, max_length=100)
    community: str = Field(default='', max_length=100)
    region: str = Field(default='US', max_length=12)
    audience: str = Field(default='', max_length=500)
    topic: str = Field(min_length=2, max_length=250)
    hook: str = Field(min_length=2, max_length=400)
    caption: str = Field(min_length=1, max_length=2200)
    script: str = Field(default='', max_length=15000)
    duration_seconds: int = Field(default=25, ge=1, le=600)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    call_to_action: str = Field(default='', max_length=500)
    offer: str = Field(default='', max_length=500)
    landing_page: HttpUrl | None = None
    goal: Literal['reach', 'leads', 'sales'] = 'reach'
    estimated_value_per_conversion: float = Field(default=0, ge=0)

    @field_validator('hashtags')
    @classmethod
    def hashtags_valid(cls, tags: list[str]) -> list[str]:
        result = []
        for raw in tags:
            tag = '#' + raw.strip().lower().lstrip('#')
            if not 2 <= len(tag) <= 65 or not tag[1:].replace('_', '').isalnum():
                raise ValueError(f'invalid hashtag {raw}')
            if tag not in result:
                result.append(tag)
        return result

class Trend(BaseModel):
    platform: Platform
    hashtag: str
    niche: str = ''
    community: str = ''
    region: str = 'US'
    posts: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)
    growth_24h: float | None = None  # relative growth e.g. 0.25 -> +25%
    observed_at: datetime
    source: str = Field(min_length=2, max_length=250)

    @field_validator('observed_at')
    @classmethod
    def normalize_observed(cls, val: datetime) -> datetime:
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val.astimezone(timezone.utc)

    @field_validator('hashtag')
    @classmethod
    def hashtag_valid(cls, tag: str) -> str:
        tag = '#' + tag.strip().lower().lstrip('#')
        if not 2 <= len(tag) <= 65 or not tag[1:].replace('_', '').isalnum():
            raise ValueError('invalid hashtag')
        return tag

class Observation(BaseModel):
    platform: Platform
    post_id: str = Field(min_length=1, max_length=150)
    caption: str = ''
    topic: str = ''
    hook: str = ''
    niche: str = ''
    duration_seconds: int = Field(default=25, ge=1, le=600)
    views: int = Field(ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    followers_at_post: int | None = Field(default=None, ge=0)
    retention_rate: float | None = Field(default=None, ge=0, le=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Campaign(BaseModel):
    campaign_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    variant_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    platform: Platform
    destination: HttpUrl

    @field_validator('destination')
    @classmethod
    def secure_destination(cls, val: HttpUrl) -> HttpUrl:
        if val.scheme != 'https':
            raise ValueError('Campaign destinations must use HTTPS')
        return val

class ConversionEvent(BaseModel):
    event_id: str = Field(min_length=8, max_length=128)
    campaign_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    variant_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    revenue: float = Field(default=0, ge=0)

class Exposure(BaseModel):
    campaign_id: str
    variant_id: str
    views: int = Field(ge=0)

class Snapshot(BaseModel):
    platform: Platform
    post_id: str = Field(min_length=1, max_length=150)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    views: int = Field(ge=0)
    likes: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    campaign_id: str | None = None
    variant_id: str | None = None

    @field_validator('observed_at')
    @classmethod
    def normalize_observed(cls, val: datetime) -> datetime:
        return val.replace(tzinfo=timezone.utc) if val.tzinfo is None else val.astimezone(timezone.utc)

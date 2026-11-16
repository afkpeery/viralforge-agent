from __future__ import annotations
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet
from .models import Trend, Observation, Campaign, ConversionEvent, Snapshot

class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as con:
            con.executescript('''
            CREATE TABLE IF NOT EXISTS oauth_states(
              state TEXT PRIMARY KEY, platform TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS credentials(
              platform TEXT PRIMARY KEY, payload BLOB NOT NULL, updated_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS posts(
              platform TEXT NOT NULL, post_id TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(platform,post_id));
            CREATE TABLE IF NOT EXISTS trends(
              platform TEXT NOT NULL, hashtag TEXT NOT NULL, region TEXT NOT NULL,
              observed_at TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(platform,hashtag,region,observed_at));
            CREATE TABLE IF NOT EXISTS snapshots(
              platform TEXT NOT NULL, post_id TEXT NOT NULL, observed_at TEXT NOT NULL, payload TEXT NOT NULL,
              PRIMARY KEY(platform,post_id,observed_at));
            CREATE TABLE IF NOT EXISTS campaigns(
              campaign_id TEXT NOT NULL, variant_id TEXT NOT NULL,
              platform TEXT NOT NULL, destination TEXT NOT NULL,
              PRIMARY KEY(campaign_id,variant_id));
            CREATE TABLE IF NOT EXISTS exposure(
              campaign_id TEXT NOT NULL, variant_id TEXT NOT NULL, views INTEGER NOT NULL,
              PRIMARY KEY(campaign_id,variant_id));
            CREATE TABLE IF NOT EXISTS clicks(
              id INTEGER PRIMARY KEY AUTOINCREMENT, campaign_id TEXT NOT NULL,
              variant_id TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS conversions(
              event_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL,
              variant_id TEXT NOT NULL, revenue REAL NOT NULL, created_at REAL NOT NULL);
            ''')

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def add_state(self, state, platform):
        with self.db() as con:
            con.execute('INSERT INTO oauth_states VALUES(?,?,?)', (state, platform, datetime.now(timezone.utc).timestamp()))

    def consume_state(self, state, platform):
        with self.db() as con:
            cursor = con.execute('DELETE FROM oauth_states WHERE state=? AND platform=? AND created_at>?',
                                 (state, platform, datetime.now(timezone.utc).timestamp()-600))
            return cursor.rowcount == 1

    def put_token(self, platform, token, key):
        encrypted = Fernet(key.encode()).encrypt(json.dumps(token).encode())
        with self.db() as con:
            con.execute('REPLACE INTO credentials VALUES(?,?,?)', (platform, encrypted, datetime.now(timezone.utc).timestamp()))

    def get_token(self, platform, key):
        with self.db() as con:
            row = con.execute('SELECT payload FROM credentials WHERE platform=?', (platform,)).fetchone()
        return json.loads(Fernet(key.encode()).decrypt(row[0]).decode()) if row else None

    def put_post(self, obs: Observation):
        with self.db() as con:
            con.execute('REPLACE INTO posts VALUES(?,?,?)',
                        (obs.platform, obs.post_id, obs.model_dump_json()))

    def posts(self, platform):
        with self.db() as con:
            rows = con.execute('SELECT payload FROM posts WHERE platform=?', (platform,)).fetchall()
        return [Observation.model_validate_json(x[0]) for x in rows]

    def put_trends(self, trends: list[Trend]):
        with self.db() as con:
            for tr in trends:
                con.execute('REPLACE INTO trends VALUES(?,?,?,?,?)',
                    (tr.platform, tr.hashtag, tr.region.upper(), tr.observed_at.isoformat(), tr.model_dump_json()))

    def trends(self, platform: str, region: str):
        with self.db() as con:
            rows = con.execute('SELECT payload FROM trends WHERE platform=? AND region=?',
                               (platform, region.upper())).fetchall()
        return [Trend.model_validate_json(x[0]) for x in rows]

    def put_campaign(self, c: Campaign):
        with self.db() as con:
            con.execute('REPLACE INTO campaigns VALUES(?,?,?,?)',
                        (c.campaign_id,c.variant_id,c.platform,str(c.destination)))

    def campaign(self, campaign, variant):
        with self.db() as con:
            row = con.execute('SELECT platform,destination FROM campaigns WHERE campaign_id=? AND variant_id=?',
                              (campaign,variant)).fetchone()
        return {'platform':row[0], 'destination':row[1]} if row else None

    def record_click(self, campaign, variant):
        with self.db() as con:
            con.execute('INSERT INTO clicks(campaign_id,variant_id,created_at) VALUES(?,?,?)',
                        (campaign,variant,datetime.now(timezone.utc).timestamp()))

    def record_conversion(self, event: ConversionEvent):
        with self.db() as con:
            row = con.execute('INSERT OR IGNORE INTO conversions VALUES(?,?,?,?,?)',
                 (event.event_id,event.campaign_id,event.variant_id,event.revenue,datetime.now(timezone.utc).timestamp()))
            return row.rowcount == 1

    def set_exposure(self, campaign, variant, views):
        with self.db() as con:
            con.execute('INSERT INTO exposure VALUES(?,?,?) ON CONFLICT(campaign_id,variant_id) '
                        'DO UPDATE SET views=excluded.views', (campaign,variant,views))

    def campaign_stats(self, campaign):
        with self.db() as con:
            rows = con.execute('''SELECT a.variant_id, a.platform, COALESCE(e.views,0),
                  (SELECT count(*) FROM clicks k WHERE k.campaign_id=a.campaign_id AND k.variant_id=a.variant_id),
                  (SELECT count(*) FROM conversions c WHERE c.campaign_id=a.campaign_id AND c.variant_id=a.variant_id),
                  (SELECT COALESCE(sum(revenue),0) FROM conversions c WHERE c.campaign_id=a.campaign_id AND c.variant_id=a.variant_id)
                  FROM campaigns a LEFT JOIN exposure e ON e.campaign_id=a.campaign_id AND e.variant_id=a.variant_id
                  WHERE a.campaign_id=?''',(campaign,)).fetchall()
        return [{'variant':r[0],'platform':r[1],'views':r[2],'clicks':r[3],'conversions':r[4],'revenue':r[5]} for r in rows]

    def put_snapshots(self, snaps: list[Snapshot]):
        with self.db() as con:
            for item in snaps:
                con.execute('REPLACE INTO snapshots VALUES(?,?,?,?)',
                    (item.platform,item.post_id,item.observed_at.isoformat(),item.model_dump_json()))

    def snapshots(self, platform):
        with self.db() as con:
            rows=con.execute('SELECT payload FROM snapshots WHERE platform=? ORDER BY observed_at',
                             (platform,)).fetchall()
        return [Snapshot.model_validate_json(x[0]) for x in rows]

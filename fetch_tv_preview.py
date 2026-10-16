#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches upcoming TV features likely to cover IH cooking heaters / kitchen
appliances, from two sources:
  1. NHK Program List API (official, exact air date/time, NHK channels only,
     needs NHK_API_KEY env var; silently skipped if not set).
  2. Google News RSS search for preview articles about commercial-broadcaster
     features (best-effort air date parsed out of the headline text).

Writes tv_preview.json in the shape update_tv_preview.py expects.

Usage:
    python3 fetch_tv_preview.py tv_preview.json
"""
import difflib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"
JST = timezone(timedelta(hours=9))

SIMILARITY_THRESHOLD = 0.85

# --- NHK Program List API -----------------------------------------------
NHK_AREA = "280"  # Hyogo (JIS prefecture code 28 x10); verify once a key is live.
NHK_SERVICES = {"g1": "NHK総合", "e1": "Eテレ"}
NHK_DAYS_AHEAD = 2  # today + 2 days (~48h), per explicit instruction.
NHK_KEYWORDS = [
    "IH", "クッキングヒーター", "電磁調理器", "IHコンロ", "IH調理器",
    "オール電化", "キッチン家電", "調理家電",
]


def fetch_nhk_day(apikey, service, date_str):
    url = f"https://api.nhk.or.jp/v2/pg/list/{NHK_AREA}/{service}/{date_str}.json?key={apikey}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read())


def matches_keyword(*texts):
    blob = " ".join(t for t in texts if t)
    return any(kw in blob for kw in NHK_KEYWORDS)


def fetch_nhk_items():
    apikey = os.environ.get("NHK_API_KEY")
    if not apikey:
        print("NHK_API_KEY not set; skipping NHK program list.", file=sys.stderr)
        return []

    items = []
    today = datetime.now(JST).date()
    for offset in range(NHK_DAYS_AHEAD + 1):
        date_str = (today + timedelta(days=offset)).isoformat()
        for service, channel_name in NHK_SERVICES.items():
            try:
                data = fetch_nhk_day(apikey, service, date_str)
            except Exception as e:
                print(f"NHK API fetch failed ({service}, {date_str}): {e}", file=sys.stderr)
                continue
            for program in data.get("list", {}).get(service, []):
                title = (program.get("title") or "").strip()
                subtitle = (program.get("subtitle") or "").strip()
                content = (program.get("content") or "").strip()
                if not matches_keyword(title, subtitle, content):
                    continue
                start = program.get("start_time")
                end = program.get("end_time")
                time_label = None
                try:
                    st = datetime.fromisoformat(start)
                    time_label = st.strftime("%H:%M")
                    if end:
                        et = datetime.fromisoformat(end)
                        time_label += "–" + et.strftime("%H:%M")
                except (TypeError, ValueError):
                    pass
                display_title = title if not subtitle else f"{title}「{subtitle}」"
                items.append({
                    "title": display_title,
                    "channel": channel_name,
                    "date": date_str,
                    "time": time_label,
                    "source_type": "nhk",
                    "source": "NHK番組表",
                    "link": None,
                })
    return items


# --- Google News preview-article search ----------------------------------
TV_CONTEXT = "(テレビ OR 放送 OR 番組) (特集 OR 紹介)"
TV_QUERY_1 = f"(IHクッキングヒーター OR IH調理器 OR 電磁調理器) {TV_CONTEXT}"
TV_QUERY_2 = f"(調理家電 OR キッチン家電) {TV_CONTEXT}"
FORWARD_WINDOW_DAYS = 10  # accept an extracted air date up to this far ahead
TONIGHT_PUBDATE_HOURS = 18  # "今夜" only trusted from a near-fresh article

DATE_IN_TITLE_RE = re.compile(r'(\d{1,2})月(\d{1,2})日')
TONIGHT_RE = re.compile(r'今夜|本日放送')


def gnews_url(query):
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ja&gl=JP&ceid=JP:ja"


def local_name(tag):
    return tag.split('}')[-1]


def parse_pubdate(item):
    for child in item:
        if local_name(child.tag) == "pubDate":
            text = (child.text or "").strip()
            try:
                dt = parsedate_to_datetime(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                continue
    return None


def item_fields(item):
    title, link, source = None, None, None
    for child in item:
        name = local_name(child.tag)
        if name == "title" and title is None:
            title = (child.text or "").strip()
        elif name == "link" and link is None:
            link = (child.text or "").strip()
        elif name == "source" and source is None:
            source = (child.text or "").strip()
    if title and source:
        title = re.sub(r'\s*-\s*' + re.escape(source) + r'$', '', title).strip()
    return title, link, source


def guess_air_date(title, now_date):
    # Only accept a date we can place in [today, today+window]; anything else
    # is either stale recap coverage of a show that already aired, or too
    # speculative to label as "upcoming" with confidence.
    m = DATE_IN_TITLE_RE.search(title)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    window_end = now_date + timedelta(days=FORWARD_WINDOW_DAYS)
    for year in (now_date.year, now_date.year + 1):
        try:
            candidate = datetime(year, month, day).date()
        except ValueError:
            continue
        if now_date <= candidate <= window_end:
            return candidate.isoformat()
    return None


def fetch_news_items():
    items = []
    now_jst = datetime.now(JST)
    today = now_jst.date()
    for query in (TV_QUERY_1, TV_QUERY_2):
        try:
            req = urllib.request.Request(gnews_url(query), headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                root = ET.fromstring(resp.read())
        except Exception as e:
            print(f"Google News fetch failed ({query}): {e}", file=sys.stderr)
            continue
        for el in root.iter():
            if local_name(el.tag) != "item":
                continue
            title, link, source = item_fields(el)
            pub = parse_pubdate(el)
            if not title or not link or pub is None:
                continue

            air_date = guess_air_date(title, today)
            if air_date is None and TONIGHT_RE.search(title) and pub >= now_jst - timedelta(hours=TONIGHT_PUBDATE_HOURS):
                air_date = today.isoformat()
            if air_date is None:
                continue  # can't confidently place it as upcoming; drop rather than mislabel

            items.append({
                "title": title,
                "channel": None,
                "date": air_date,
                "time": None,
                "source_type": "news",
                "source": source or "ニュース",
                "link": link,
            })
    return items


def normalize_title(title):
    return re.sub(r'[（(][^（）()]{1,20}[）)]\s*$', '', title).strip()


def is_near_duplicate(a, b):
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= SIMILARITY_THRESHOLD


def dedupe(items):
    # NHK items are more precise; keep them over a near-duplicate news item.
    ordered = [it for it in items if it["source_type"] == "nhk"] + [it for it in items if it["source_type"] == "news"]
    kept = []
    for it in ordered:
        if any(is_near_duplicate(it["title"], k["title"]) for k in kept):
            continue
        kept.append(it)
    return kept


def sort_key(it):
    has_date = it["date"] is not None
    return (0 if has_date else 1, it["date"] or "", it["time"] or "")


def main(out_path):
    items = fetch_nhk_items() + fetch_news_items()
    items = dedupe(items)
    items.sort(key=sort_key)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": items, "generated_at": datetime.now(JST).isoformat()}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(items)} TV preview items.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_tv_preview.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

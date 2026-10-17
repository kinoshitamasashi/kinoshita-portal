#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches upcoming TV features likely to cover kitchen appliances (IH cooking
heaters etc.), via Google News RSS search for preview articles. Air date is
best-effort parsed out of the headline text; items where no near-term date
can be confidently extracted are dropped rather than mislabeled as upcoming.

Writes tv_preview.json in the shape update_tv_preview.py expects.

Usage:
    python3 fetch_tv_preview.py tv_preview.json
"""
import difflib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"
JST = timezone(timedelta(hours=9))
SIMILARITY_THRESHOLD = 0.85

TV_CONTEXT = "(テレビ OR 放送 OR 番組) (特集 OR 紹介)"
TV_QUERY_1 = f"(IHクッキングヒーター OR IH調理器 OR 電磁調理器) {TV_CONTEXT}"
TV_QUERY_2 = f"(調理家電 OR キッチン家電) {TV_CONTEXT}"
FORWARD_WINDOW_DAYS = 10  # accept an extracted air date up to this far ahead
TONIGHT_PUBDATE_HOURS = 18  # "今夜" only trusted from a near-fresh article
PUBDATE_MAX_AGE_DAYS = 45  # old recurring-segment articles get resurfaced by
                           # keyword match; a stale pubDate means the "27日"
                           # in the title is about some past year, not this one

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
            if pub < now_jst - timedelta(days=PUBDATE_MAX_AGE_DAYS):
                continue  # stale/recurring-segment article resurfaced by keyword match

            air_date = guess_air_date(title, today)
            if air_date is None and TONIGHT_RE.search(title) and pub >= now_jst - timedelta(hours=TONIGHT_PUBDATE_HOURS):
                air_date = today.isoformat()
            if air_date is None:
                continue  # can't confidently place it as upcoming; drop rather than mislabel

            items.append({
                "title": title,
                "date": air_date,
                "source": source or "ニュース",
                "link": link,
            })
    return items


def normalize_title(title):
    return re.sub(r'[（(][^（）()]{1,20}[）)]\s*$', '', title).strip()


def is_near_duplicate(a, b):
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= SIMILARITY_THRESHOLD


def dedupe(items):
    kept = []
    for it in items:
        if any(is_near_duplicate(it["title"], k["title"]) for k in kept):
            continue
        kept.append(it)
    return kept


def main(out_path):
    items = dedupe(fetch_news_items())
    items.sort(key=lambda it: it["date"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": items, "generated_at": datetime.now(JST).isoformat()}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(items)} TV preview items.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_tv_preview.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

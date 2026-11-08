#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches articles about TV segments that already aired covering kitchen
appliances (IH cooking heaters etc.), via Google News RSS search for
tie-in/recap coverage ("テレビで紹介された...") rather than advance previews.
Preview-style announcements with a forward air date turned out to be far too
rare to populate this section (the query matched almost nothing); recap
coverage published once a segment has aired is much more abundant (recurring
series from ノジマ, 知っ得レシピ, ヨムーノ etc.), so the article's own pubDate
is used directly as the display date instead of trying to extract a future
air date from the headline.

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
# Bare "キッチン" alone pulls in restaurant names, drama titles and kids'
# shows (e.g. a cafe literally named "...キッチン", "キッチン戦隊クックルン"),
# so kitchen coverage is scoped to systems/renovation rather than the bare
# word; plain kitchen sundries (100円ショップ goods etc.) are left out as
# too far from the department's actual interest.
TV_QUERY_2 = f"(調理家電 OR キッチン家電 OR システムキッチン OR キッチンリフォーム) {TV_CONTEXT}"
PUBDATE_MAX_AGE_DAYS = 45  # drop old recurring-segment articles resurfaced by
                           # keyword match; recap coverage is only useful here
                           # while reasonably recent


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


def fetch_news_items():
    items = []
    now_jst = datetime.now(JST)
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

            items.append({
                "title": title,
                "date": pub.astimezone(JST).date().isoformat(),
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
    items.sort(key=lambda it: it["date"], reverse=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": items, "generated_at": datetime.now(JST).isoformat()}, f, ensure_ascii=False, indent=2)
    print(f"Wrote {len(items)} TV preview items.", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_tv_preview.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

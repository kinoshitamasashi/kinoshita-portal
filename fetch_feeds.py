#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches the curated RSS/RDF feeds directly over HTTP and writes feed_data.json
in the shape update_news.py expects. Meant to run in an environment with real
outbound network access (e.g. GitHub Actions), not the CCR cloud sandbox.

Usage:
    python3 fetch_feeds.py feed_data.json
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"

IH_QUERY = "IHクッキングヒーター OR 電磁調理器 OR IHコンロ OR IH調理器"

FEEDS = [
    {"url": "https://kaden.watch.impress.co.jp/data/rss/1.0/kdw/feed.rdf", "source": "家電Watch", "cat": "appliance"},
    {"url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml", "source": "ITmedia AI+", "cat": "ai"},
    {"url": "https://foodtech-japan.com/feed/", "source": "Foovo", "cat": "food"},
    {"url": "https://www.housenews.jp/feed", "source": "住宅産業新聞", "cat": "food"},
    {"url": "https://toyokeizai.net/list/feed/rss", "source": "東洋経済オンライン", "cat": "magazine"},
    {"url": "https://diamond.jp/list/feed/rss/dol", "source": "ダイヤモンド・オンライン", "cat": "magazine"},
    {"url": "https://gekirock.com/news/index.xml", "source": "激ロック", "cat": "rock"},
    {
        "url": "https://news.google.com/rss/search?q=" + urllib.parse.quote(IH_QUERY) + "&hl=ja&gl=JP&ceid=JP:ja",
        "source": None,
        "cat": "ih_focus",
    },
]

TOP_N = {"appliance": 15, "ai": 15, "magazine": 18, "food": 15, "rock": 15, "ih_focus": 12}


def local_name(tag):
    return tag.split('}')[-1]


def parse_date(item):
    for child in item:
        name = local_name(child.tag)
        text = (child.text or "").strip()
        if not text:
            continue
        if name == "pubDate":
            try:
                dt = parsedate_to_datetime(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                continue
        if name == "date":
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return ET.fromstring(raw)


def extract_items(root):
    items = []
    for el in root.iter():
        if local_name(el.tag) == "item":
            items.append(el)
    return items


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


def main(out_path):
    result = {"appliance": [], "ai": [], "magazine": [], "food": [], "rock": [], "ih_focus": []}
    errors = []

    for feed in FEEDS:
        try:
            root = fetch_feed(feed["url"])
            items = extract_items(root)
            for item in items:
                title, link, item_source = item_fields(item)
                dt = parse_date(item)
                source = feed["source"] or item_source
                if not title or not link or dt is None or not source:
                    continue
                result[feed["cat"]].append({
                    "title": title,
                    "link": link,
                    "date": dt.strftime("%Y-%m-%d"),
                    "source": source,
                    "_sort": dt,
                })
        except Exception as e:
            errors.append(f"{feed['source'] or feed['cat']} ({feed['url']}): {e}")

    for cat in result:
        result[cat].sort(key=lambda x: x["_sort"], reverse=True)
        seen_titles = set()
        deduped = []
        for it in result[cat]:
            del it["_sort"]
            if it["title"] in seen_titles:
                continue
            seen_titles.add(it["title"])
            deduped.append(it)
        result[cat] = deduped[:TOP_N[cat]]
        if not result[cat]:
            errors.append(f"category '{cat}' ended up empty")

    if errors:
        print("WARNINGS:\n" + "\n".join(errors), file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if any(not result[cat] for cat in result):
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_feeds.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

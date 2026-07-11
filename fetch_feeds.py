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
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"

FEEDS = [
    {"url": "https://kaden.watch.impress.co.jp/data/rss/1.0/kdw/feed.rdf", "source": "家電Watch", "cat": "appliance"},
    {"url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml", "source": "ITmedia AI+", "cat": "ai"},
    {"url": "https://foodtech-japan.com/feed/", "source": "Foovo", "cat": "food"},
    {"url": "https://www.housenews.jp/feed", "source": "住宅産業新聞", "cat": "food"},
    {"url": "https://toyokeizai.net/list/feed/rss", "source": "東洋経済オンライン", "cat": "magazine"},
    {"url": "https://diamond.jp/list/feed/rss/dol", "source": "ダイヤモンド・オンライン", "cat": "magazine"},
    {"url": "https://gekirock.com/news/index.xml", "source": "激ロック", "cat": "rock"},
]

TOP_N = {"appliance": 15, "ai": 15, "magazine": 18, "food": 15, "rock": 15}


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
    title, link = None, None
    for child in item:
        name = local_name(child.tag)
        if name == "title" and title is None:
            title = (child.text or "").strip()
        elif name == "link" and link is None:
            link = (child.text or "").strip()
    return title, link


def main(out_path):
    result = {"appliance": [], "ai": [], "magazine": [], "food": [], "rock": []}
    errors = []

    for feed in FEEDS:
        try:
            root = fetch_feed(feed["url"])
            items = extract_items(root)
            for item in items:
                title, link = item_fields(item)
                dt = parse_date(item)
                if not title or not link or dt is None:
                    continue
                result[feed["cat"]].append({
                    "title": title,
                    "link": link,
                    "date": dt.strftime("%Y-%m-%d"),
                    "source": feed["source"],
                    "_sort": dt,
                })
        except Exception as e:
            errors.append(f"{feed['source']} ({feed['url']}): {e}")

    for cat in result:
        result[cat].sort(key=lambda x: x["_sort"], reverse=True)
        for it in result[cat]:
            del it["_sort"]
        result[cat] = result[cat][:TOP_N[cat]]
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

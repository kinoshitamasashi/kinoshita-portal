#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches the curated RSS/RDF feeds directly over HTTP and writes feed_data.json
in the shape update_news.py expects. Meant to run in an environment with real
outbound network access (e.g. GitHub Actions), not the CCR cloud sandbox.

Usage:
    python3 fetch_feeds.py feed_data.json
"""
import difflib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SIMILARITY_THRESHOLD = 0.85
DUP_WINDOW_DAYS = 1


def normalize_title(title):
    # strip trailing attribution/page markers like "（デイリー新潮）" or "(2ページ目)"
    return re.sub(r'[（(][^（）()]{1,20}[）)]\s*$', '', title).strip()


def is_near_duplicate(a, b):
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= SIMILARITY_THRESHOLD


MAX_PER_ENTITY_CLUSTER = 2


def extract_entity_tokens(title):
    # Distinctive proper-noun-ish tokens (brand names etc.), used to cap how many
    # articles about the same single event (same day, same named entity) pile up.
    return set(re.findall(r'[ァ-ヴー]{4,}', title))


def shares_entity(a_tokens, b_tokens):
    return bool(a_tokens & b_tokens)


# Sources known to commonly paywall full articles (best-effort heuristic;
# RSS metadata doesn't expose per-article paywall status).
PAYWALLED_SOURCES = {
    "日本経済新聞", "日経電子版", "日経ビジネス", "日経ビジネス電子版",
    "日経クロステック", "日経xTECH", "Bloomberg", "ウォール・ストリート・ジャーナル", "WSJ",
}


def is_paywalled(source):
    return source in PAYWALLED_SOURCES


UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"

IH_QUERY = "IHクッキングヒーター OR 電磁調理器 OR IHコンロ OR IH調理器"
IOT_QUERY = "IoT家電 OR スマート家電 OR コネクテッド家電 OR スマートキッチン"
KITCHEN_QUERY = "システムキッチン OR Miele OR タカラスタンダード OR クリナップ"
AI_QUERY = "ChatGPT OR Claude OR Copilot"
FOODTECH_QUERY = "フードテック OR 自動調理 OR 調理家電"
BIGNEWS_QUERY = (
    "(家電メーカー OR 住宅メーカー OR キッチンメーカー OR 家電量販店 OR 住宅設備 OR IHクッキングヒーター) "
    "(買収 OR 経営統合 OR 合併 OR 資本提携)"
)
BIGNEWS_GLOBAL_QUERY = (
    "(Samsung OR LG電子 OR Whirlpool OR Electrolux OR Haier OR ハイアール OR Midea OR 美的 OR GEアプライアンス) "
    "(家電 OR 住宅設備 OR 白物家電) "
    "(買収 OR 経営統合 OR 合併 OR M&A)"
)
BIGNEWS_TECH_QUERY = (
    "(家電 OR IHクッキングヒーター OR キッチン家電 OR 住宅設備 OR 省エネ住宅) "
    "(技術革新 OR 新技術開発 OR ブレークスルー)"
)
TOC_QUERY = "制約理論 OR ゴールドラット OR スループット会計 OR 制約条件理論"

def gnews(query):
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ja&gl=JP&ceid=JP:ja"


FEEDS = [
    {"url": "https://kaden.watch.impress.co.jp/data/rss/1.0/kdw/feed.rdf", "source": "家電Watch", "cat": "appliance"},
    {"url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml", "source": "ITmedia AI+", "cat": "ai"},
    {"url": "https://foodtech-japan.com/feed/", "source": "Foovo", "cat": "food"},
    {"url": "https://www.housenews.jp/feed", "source": "住宅産業新聞", "cat": "food"},
    {"url": "https://toyokeizai.net/list/feed/rss", "source": "東洋経済オンライン", "cat": "magazine"},
    {"url": "https://diamond.jp/list/feed/rss/dol", "source": "ダイヤモンド・オンライン", "cat": "magazine"},
    {"url": "https://gekirock.com/news/index.xml", "source": "激ロック", "cat": "rock"},
    {"url": gnews(IH_QUERY), "source": None, "cat": "ih_focus"},
    {"url": gnews(IOT_QUERY), "source": None, "cat": "ih_focus"},
    {"url": gnews(KITCHEN_QUERY), "source": None, "cat": "food"},
    {"url": gnews(AI_QUERY), "source": None, "cat": "ai"},
    {"url": gnews(FOODTECH_QUERY), "source": None, "cat": "food"},
    {"url": gnews(BIGNEWS_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(BIGNEWS_GLOBAL_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(BIGNEWS_TECH_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(TOC_QUERY), "source": None, "cat": "toc"},
]

TOP_N = {"appliance": 15, "ai": 15, "magazine": 18, "food": 15, "rock": 15, "ih_focus": 16, "big_news": 35, "toc": 15}


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
    result = {"appliance": [], "ai": [], "magazine": [], "food": [], "rock": [], "ih_focus": [], "big_news": [], "toc": []}
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
        deduped = []
        for it in result[cat]:
            del it["_sort"]
            it_date = datetime.strptime(it["date"], "%Y-%m-%d").date()
            dup_index = None
            for idx, kept in enumerate(deduped):
                kept_date = datetime.strptime(kept["date"], "%Y-%m-%d").date()
                if abs((it_date - kept_date).days) <= DUP_WINDOW_DAYS and is_near_duplicate(it["title"], kept["title"]):
                    dup_index = idx
                    break
            if dup_index is not None:
                kept = deduped[dup_index]
                if is_paywalled(kept["source"]) and not is_paywalled(it["source"]):
                    deduped[dup_index] = it
                continue

            # cap how many articles about the same single event (same brand-name
            # token, same narrow date window) can pile up from heavy syndication
            it_tokens = extract_entity_tokens(it["title"])
            if it_tokens:
                cluster_count = 0
                for kept in deduped:
                    kept_date = datetime.strptime(kept["date"], "%Y-%m-%d").date()
                    if abs((it_date - kept_date).days) <= DUP_WINDOW_DAYS and shares_entity(it_tokens, extract_entity_tokens(kept["title"])):
                        cluster_count += 1
                if cluster_count >= MAX_PER_ENTITY_CLUSTER:
                    continue

            deduped.append(it)
        result[cat] = deduped[:TOP_N[cat]]
        if not result[cat]:
            errors.append(f"category '{cat}' ended up empty")

    if errors:
        print("WARNINGS:\n" + "\n".join(errors), file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if all(not result[cat] for cat in result):
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_feeds.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

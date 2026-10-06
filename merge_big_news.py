#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Accumulates "big news" (industry M&A / major business moves) across daily runs
so a story stays visible for about a month even if it later drops out of the
day's freshest search results.

Reads feed_data.json's "big_news" list (today's freshly fetched candidates),
merges them into the persisted big_news_state.json, drops anything older than
RETENTION_DAYS, collapses near-duplicate titles (regardless of how many days
apart they were captured, preferring a non-paywalled source when choosing
which copy to keep), and writes the result back into BOTH files so
update_news.py simply splices feed_data.json as usual.

Usage:
    python3 merge_big_news.py feed_data.json big_news_state.json
"""
import difflib
import json
import re
import sys
from datetime import date, timedelta

RETENTION_DAYS = 30
SIMILARITY_THRESHOLD = 0.85

PAYWALLED_SOURCES = {
    "日本経済新聞", "日経電子版", "日経ビジネス", "日経ビジネス電子版",
    "日経クロステック", "日経xTECH", "Bloomberg", "ウォール・ストリート・ジャーナル", "WSJ",
}


def normalize_title(title):
    return re.sub(r'[（(][^（）()]{1,20}[）)]\s*$', '', title).strip()


def is_near_duplicate(a, b):
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= SIMILARITY_THRESHOLD


def is_paywalled(source):
    return source in PAYWALLED_SOURCES


def main(feed_data_path, state_path):
    with open(feed_data_path, 'r', encoding='utf-8-sig') as f:
        feed_data = json.load(f)
    fresh_items = feed_data.get("big_news", [])

    try:
        with open(state_path, 'r', encoding='utf-8-sig') as f:
            state = json.load(f)
    except FileNotFoundError:
        state = []

    by_link = {it["link"]: it for it in state}
    for it in fresh_items:
        by_link.setdefault(it["link"], it)

    cutoff = date.today() - timedelta(days=RETENTION_DAYS)
    candidates = [it for it in by_link.values() if date.fromisoformat(it["date"]) >= cutoff]
    candidates.sort(key=lambda x: x["date"], reverse=True)

    deduped = []
    for it in candidates:
        dup_index = None
        for idx, kept in enumerate(deduped):
            if is_near_duplicate(it["title"], kept["title"]):
                dup_index = idx
                break
        if dup_index is not None:
            kept = deduped[dup_index]
            if is_paywalled(kept["source"]) and not is_paywalled(it["source"]):
                deduped[dup_index] = it
            continue
        deduped.append(it)

    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    feed_data["big_news"] = deduped
    with open(feed_data_path, 'w', encoding='utf-8') as f:
        json.dump(feed_data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 merge_big_news.py <feed_data.json> <big_news_state.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

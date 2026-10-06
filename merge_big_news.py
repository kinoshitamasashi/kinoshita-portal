#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Accumulates "big news" (industry M&A / major business moves) across daily runs
so a story stays visible for about a month even if it later drops out of the
day's freshest search results.

Reads feed_data.json's "big_news" list (today's freshly fetched candidates),
merges them into the persisted big_news_state.json (deduped by link), drops
anything older than RETENTION_DAYS, and writes the merged/filtered list back
into BOTH files so update_news.py simply splices feed_data.json as usual.

Usage:
    python3 merge_big_news.py feed_data.json big_news_state.json
"""
import json
import sys
from datetime import date, timedelta

RETENTION_DAYS = 30


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
    merged = [it for it in by_link.values() if date.fromisoformat(it["date"]) >= cutoff]
    merged.sort(key=lambda x: x["date"], reverse=True)

    with open(state_path, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    feed_data["big_news"] = merged
    with open(feed_data_path, 'w', encoding='utf-8') as f:
        json.dump(feed_data, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 merge_big_news.py <feed_data.json> <big_news_state.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

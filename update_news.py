#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Splices pre-fetched RSS items (as JSON) into the news categories in index.html.

This script does NOT make any network requests itself. Outbound network calls
from the cloud sandbox's Bash are blocked by policy, so feed fetching must be
done via the WebFetch tool (Anthropic-mediated) BEFORE running this script.

Expected input JSON shape (see feed_data.json):
{
  "appliance": [{"title": "...", "link": "...", "date": "2026-07-11"}, ...],
  "food":      [...],
  "ai":        [...],
  "magazine":  [...]
}

Usage:
    python3 update_news.py index.html feed_data.json
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape

JST = timezone(timedelta(hours=9))

TOP_N = {"appliance": 22, "ai": 8, "magazine": 18, "food": 17, "rock": 15, "ih_focus": 20, "toc": 21, "policy": 15, "local_news": 18}
COLOR_FOR_CAT = {"ih_focus": "#D9560E", "appliance": "#2C6E9E", "food": "#3D8B5F", "ai": "#1E8F86", "policy": "#4A6572", "magazine": "#B08A2E", "rock": "#8B2635", "toc": "#7952B3", "local_news": "#C2487A"}
CATEGORY_LABEL = {
    "ih_focus": "IH・調理家電",
    "appliance": "業界ニュース",
    "food": "食・生活",
    "ai": "AI関連",
    "policy": "政策・規制・基準",
    "magazine": "雑誌記事",
    "rock": "ロック・メタル",
    "toc": "TOC・ビジネス書・仕事術",
    "local_news": "地域ニュース",
}
HIGHLIGHTS_PER_CAT = 2
HIGHLIGHTS_TOTAL = 8
BIGNEWS_DISPLAY_CAP = 20
# Gas-stove items earn a reserved floor here too, not just in the
# fetch-side retention pool -- otherwise a quiet week for IH-specific
# subcats could still crowd gas items out of the displayed top 20 by
# pure recency.
BIGNEWS_DISPLAY_RESERVED = {"gas_product": 2, "gas_tech": 1}


def apply_bignews_display_reservation(items, reserved, cap):
    order = {id(it): i for i, it in enumerate(items)}
    selected = []
    for subcat, floor in reserved.items():
        bucket = [it for it in items if it.get("_subcat") == subcat]
        selected += bucket[:floor]
    remaining = cap - len(selected)
    if remaining > 0:
        selected_ids = {id(it) for it in selected}
        leftover = [it for it in items if id(it) not in selected_ids]
        selected += leftover[:remaining]
    selected.sort(key=lambda x: order[id(x)])
    return selected


def build_rows(items):
    rows = []
    for it in items:
        title = escape(it["title"])
        source = escape(it["source"])
        date_str = it["date"].replace("-", "/")
        url = escape(it["link"], quote=True)
        rows.append(
            f'        <a class="link-row" target="_blank" rel="noopener noreferrer" href="{url}">\n'
            f'          <span class="link-bar"></span>\n'
            f'          <span class="link-text">\n'
            f'            <div class="link-title">{title}</div>\n'
            f'            <div class="link-src mono">{source} ・ {date_str}</div>\n'
            f'          </span>\n'
            f'          <span class="go">›</span>\n'
            f'        </a>\n'
        )
    return ''.join(rows)


def build_highlight_rows(data):
    candidates = []
    for cat, color in COLOR_FOR_CAT.items():
        for it in data.get(cat, [])[:HIGHLIGHTS_PER_CAT]:
            candidates.append((it, cat, color))
    candidates.sort(key=lambda x: x[0]["date"], reverse=True)
    candidates = candidates[:HIGHLIGHTS_TOTAL]

    rows = []
    for it, cat, color in candidates:
        title = escape(it["title"])
        source = escape(it["source"])
        date_str = it["date"].replace("-", "/")
        url = escape(it["link"], quote=True)
        label = CATEGORY_LABEL[cat]
        rows.append(
            f'        <a class="link-row" target="_blank" rel="noopener noreferrer" href="{url}">\n'
            f'          <span class="link-bar" style="--cat-color:{color}"></span>\n'
            f'          <span class="link-text">\n'
            f'            <div class="link-title"><span class="tag" style="--tag-color:{color}">{label}</span>{title}</div>\n'
            f'            <div class="link-src mono">{source} ・ {date_str}</div>\n'
            f'          </span>\n'
            f'          <span class="go">›</span>\n'
            f'        </a>\n'
        )
    return ''.join(rows)


def replace_highlights_body(html, new_rows):
    anchor = '<div class="highlights">'
    s = html.find(anchor)
    if s < 0:
        raise RuntimeError("highlights anchor not found")
    body_tag = '<div class="cat-body">'
    body_idx = html.find(body_tag, s)
    body_tag_end = body_idx + len(body_tag)
    close_end = find_matching_div_end(html, body_tag_end)
    if close_end < 0:
        raise RuntimeError("matching close div not found for highlights")
    close_start = close_end - len('</div>')
    return html[:body_tag_end] + '\n' + new_rows + '      ' + html[close_start:]


def replace_bignews_body(html, new_rows):
    anchor = '<div class="highlights big-news">'
    s = html.find(anchor)
    if s < 0:
        raise RuntimeError("big-news anchor not found")
    body_tag = '<div class="cat-body">'
    body_idx = html.find(body_tag, s)
    body_tag_end = body_idx + len(body_tag)
    close_end = find_matching_div_end(html, body_tag_end)
    if close_end < 0:
        raise RuntimeError("matching close div not found for big-news")
    close_start = close_end - len('</div>')
    return html[:body_tag_end] + '\n' + new_rows + '      ' + html[close_start:]


def find_matching_div_end(html, after_open_div_tag_end):
    depth = 1
    for m in re.finditer(r'<div\b|</div>', html[after_open_div_tag_end:]):
        if m.group() == '</div>':
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return after_open_div_tag_end + m.end()
    return -1


def replace_category_body(html, color_hex, new_rows):
    anchor_open = f'<details class="cat" open style="--cat-color:{color_hex}">'
    anchor_plain = f'<details class="cat" style="--cat-color:{color_hex}">'
    s = html.find(anchor_open)
    if s < 0:
        s = html.find(anchor_plain)
    if s < 0:
        raise RuntimeError(f"anchor not found: {color_hex}")
    body_tag = '<div class="cat-body">'
    body_idx = html.find(body_tag, s)
    body_tag_end = body_idx + len(body_tag)
    close_end = find_matching_div_end(html, body_tag_end)
    if close_end < 0:
        raise RuntimeError(f"matching close div not found for {color_hex}")
    close_start = close_end - len('</div>')
    return html[:body_tag_end] + '\n' + new_rows + '      ' + html[close_start:]


def main(html_path, data_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    with open(data_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    for cat, color in COLOR_FOR_CAT.items():
        items = data.get(cat, [])[:TOP_N[cat]]
        if not items:
            print(f"WARNING: no items for category '{cat}', skipping (keeping existing content)", file=sys.stderr)
            continue
        rows = build_rows(items)
        html = replace_category_body(html, color, rows)

    highlight_rows = build_highlight_rows(data)
    if not highlight_rows:
        raise RuntimeError("no highlight items generated - refusing to wipe existing content")
    html = replace_highlights_body(html, highlight_rows)

    big_news_items = apply_bignews_display_reservation(
        data.get("big_news", []), BIGNEWS_DISPLAY_RESERVED, BIGNEWS_DISPLAY_CAP
    )
    if big_news_items:
        html = replace_bignews_body(html, build_rows(big_news_items))
    else:
        print("WARNING: no big_news items, skipping (keeping existing content)", file=sys.stderr)

    timestamp = datetime.now(timezone.utc).astimezone(JST).strftime("%Y/%m/%d %H:%M")
    html = re.sub(r'記事一覧 最終更新: \d{4}/\d{2}/\d{2}(?: \d{2}:\d{2})?', f'記事一覧 最終更新: {timestamp}', html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("DONE", file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 update_news.py <index.html> <feed_data.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

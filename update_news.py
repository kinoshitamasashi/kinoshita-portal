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
from datetime import datetime
from html import escape

TOP_N = {"appliance": 15, "ai": 15, "magazine": 18, "food": 15}
COLOR_FOR_CAT = {"appliance": "#2C6E9E", "food": "#3D8B5F", "ai": "#1E8F86", "magazine": "#B08A2E"}


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
            raise RuntimeError(f"no items provided for category '{cat}' - refusing to wipe existing content")
        rows = build_rows(items)
        html = replace_category_body(html, color, rows)

    today = datetime.now().strftime("%Y/%m/%d")
    html = re.sub(r'記事一覧 最終更新: \d{4}/\d{2}/\d{2}', f'記事一覧 最終更新: {today}', html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("DONE", file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 update_news.py <index.html> <feed_data.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

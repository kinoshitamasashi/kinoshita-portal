#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Splices pre-fetched TV-preview items (tv_preview.json, from
fetch_tv_preview.py) into the "テレビ特集予告" card in index.html.

Usage:
    python3 update_tv_preview.py index.html tv_preview.json
"""
import json
import re
import sys
from datetime import datetime
from html import escape

MAX_DISPLAY = 12
WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


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


def build_row(it):
    title = escape(it["title"])
    d = datetime.strptime(it["date"], "%Y-%m-%d").date()
    date_badge = (
        f'<span class="sched-date"><span class="sched-day">{d.day}</span>'
        f'<span class="sched-dow">{WEEKDAY_JA[d.weekday()]}</span></span>'
    )
    sub = escape(it["source"]) + " ・ ニュース予告"
    url = escape(it["link"], quote=True)
    return (
        f'        <a class="sched-row" target="_blank" rel="noopener noreferrer" href="{url}">\n'
        f'          {date_badge}\n'
        f'          <span class="sched-info">\n'
        f'            <span class="sched-title">{title}</span>\n'
        f'            <span class="sched-time mono">{sub}</span>\n'
        f'          </span>\n'
        f'          <span class="go">›</span>\n'
        f'        </a>\n'
    )


def build_rows(items):
    return ''.join(build_row(it) for it in items[:MAX_DISPLAY])


def replace_tv_preview_body(html, new_rows, count):
    anchor = '<div class="tv-preview-list">'
    s = html.find(anchor)
    if s < 0:
        raise RuntimeError("tv-preview-list anchor not found")
    body_tag_end = s + len(anchor)
    close_end = find_matching_div_end(html, body_tag_end)
    if close_end < 0:
        raise RuntimeError("matching close div not found for tv-preview-list")
    close_start = close_end - len('</div>')
    if new_rows:
        body = '\n' + new_rows + '      '
    else:
        body = '\n        <p class="tv-preview-empty">直近10日で該当する特集予定は見つかりませんでした。</p>\n      '
    html = html[:body_tag_end] + body + html[close_start:]

    count_label = f"{count}件" if count else "情報なし"
    html = re.sub(
        r'(<span class="tv-preview-count mono">)[^<]*(</span>)',
        rf'\g<1>{count_label}\g<2>',
        html,
    )
    return html


def main(html_path, data_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    with open(data_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    items = data.get("items", [])[:MAX_DISPLAY]
    rows = build_rows(items)
    html = replace_tv_preview_body(html, rows, len(items))

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"DONE ({len(items)} items)", file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 update_tv_preview.py <index.html> <tv_preview.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

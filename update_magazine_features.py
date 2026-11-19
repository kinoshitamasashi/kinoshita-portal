#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Splices pre-fetched magazine feature headlines (magazine_features.json, from
fetch_magazine_features.py) into the "ビジネス誌の特集" card in index.html.

Usage:
    python3 update_magazine_features.py index.html magazine_features.json
"""
import json
import re
import sys
from html import escape


def find_matching_div_end(html_text, after_open_div_tag_end):
    depth = 1
    for m in re.finditer(r'<div\b|</div>', html_text[after_open_div_tag_end:]):
        if m.group() == '</div>':
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return after_open_div_tag_end + m.end()
    return -1


def build_row(it):
    title = escape(it["title"]) if it.get("title") else escape(it["name"])
    if it.get("title"):
        sub = escape(it["name"])
        if it.get("issue"):
            sub += " ・ " + escape(it["issue"])
    else:
        sub = "最新号の特集を確認"
    url = escape(it["link"], quote=True)
    return (
        f'        <a class="link-row" target="_blank" rel="noopener noreferrer" href="{url}">\n'
        f'          <span class="link-bar"></span>\n'
        f'          <span class="link-text">\n'
        f'            <div class="link-title">{title}</div>\n'
        f'            <div class="link-src mono">{sub}</div>\n'
        f'          </span>\n'
        f'          <span class="go">›</span>\n'
        f'        </a>\n'
    )


def build_rows(items):
    return ''.join(build_row(it) for it in items)


def replace_body(html_text, new_rows):
    anchor = '<div class="cat-body" id="magazine-features-body">'
    s = html_text.find(anchor)
    if s < 0:
        raise RuntimeError("magazine-features-body anchor not found")
    body_tag_end = s + len(anchor)
    close_end = find_matching_div_end(html_text, body_tag_end)
    if close_end < 0:
        raise RuntimeError("matching close div not found for magazine-features-body")
    close_start = close_end - len('</div>')
    body = '\n' + new_rows + '      '
    return html_text[:body_tag_end] + body + html_text[close_start:]


def main(html_path, data_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html_text = f.read()
    with open(data_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    items = data.get("items", [])
    rows = build_rows(items)
    html_text = replace_body(html_text, rows)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_text)
    print(f"DONE ({len(items)} items)", file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 update_magazine_features.py <index.html> <magazine_features.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

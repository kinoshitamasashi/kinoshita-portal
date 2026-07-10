#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches curated RSS feeds and refreshes the news categories in index.html.
Run daily. No web search / no LLM judgment required - pure feed fetch + sort.
"""
import re
import sys
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import escape
from xml.etree import ElementTree as ET

FEEDS = [
    {"name": "家電Watch", "url": "https://kaden.watch.impress.co.jp/data/rss/1.0/kdw/feed.rdf", "cat": "appliance"},
    {"name": "ITmedia AI+", "url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml", "cat": "ai"},
    {"name": "日経xTECH", "url": "https://xtech.nikkei.com/rss/index.rdf", "cat": "magazine"},
    {"name": "東洋経済オンライン", "url": "http://toyokeizai.net/list/feed/rss", "cat": "magazine"},
    {"name": "日経ビジネス電子版", "url": "https://business.nikkei.com/rss/sns/nb.rdf", "cat": "magazine"},
    {"name": "ダイヤモンド・オンライン", "url": "https://diamond.jp/list/feed/rss/dol", "cat": "magazine"},
    {"name": "住宅産業新聞", "url": "https://www.housenews.jp/feed", "cat": "food"},
    {"name": "Food Tech Media Japan", "url": "https://foodtech-japan.com/feed/", "cat": "food"},
]

TOP_N = {"appliance": 15, "ai": 15, "magazine": 18, "food": 15}
COLOR_FOR_CAT = {"appliance": "#2C6E9E", "food": "#3D8B5F", "ai": "#1E8F86", "magazine": "#B08A2E"}

UA = "Mozilla/5.0 (compatible; kinoshita-portal-bot/1.0)"


def local(tag):
    return tag.split('}')[-1] if '}' in tag else tag


def parse_date(s):
    if not s:
        return None
    s = s.strip()
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s)
    except Exception:
        pass
    return None


def fetch_items(feed):
    req = urllib.request.Request(feed["url"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    items = []
    for item in root.iter():
        if local(item.tag) != 'item':
            continue
        title = link = date_raw = None
        for child in item:
            ln = local(child.tag)
            if ln == 'title' and title is None:
                title = (child.text or '').strip()
            elif ln == 'link' and link is None:
                link = (child.text or '').strip()
            elif ln in ('pubDate', 'date') and date_raw is None:
                date_raw = (child.text or '').strip()
        dt = parse_date(date_raw)
        if not (title and link and dt):
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        items.append({"title": title, "link": link, "date": dt, "source": feed["name"]})
    return items


def build_rows(items):
    rows = []
    for it in items:
        title = escape(it["title"])
        source = escape(it["source"])
        date_str = it["date"].strftime("%Y/%m/%d")
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
    close_start = close_end - len('</div>')
    return html[:body_tag_end] + '\n' + new_rows + '      ' + html[close_start:]


def main(html_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()

    by_cat = {"appliance": [], "ai": [], "magazine": [], "food": []}
    for feed in FEEDS:
        try:
            items = fetch_items(feed)
            by_cat[feed["cat"]].extend(items)
            print(f'{feed["name"]}: {len(items)} items OK', file=sys.stderr)
        except Exception as e:
            print(f'{feed["name"]}: FAILED {e}', file=sys.stderr)

    for cat in by_cat:
        by_cat[cat].sort(key=lambda x: x["date"], reverse=True)
        by_cat[cat] = by_cat[cat][:TOP_N[cat]]
        print(f'{cat}: final {len(by_cat[cat])} items', file=sys.stderr)

    for cat, color in COLOR_FOR_CAT.items():
        rows = build_rows(by_cat[cat])
        html = replace_category_body(html, color, rows)

    today = datetime.now().strftime("%Y/%m/%d")
    html = re.sub(r'記事一覧 最終更新: \d{4}/\d{2}/\d{2}', f'記事一覧 最終更新: {today}', html)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("DONE", file=sys.stderr)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'index.html'
    main(path)

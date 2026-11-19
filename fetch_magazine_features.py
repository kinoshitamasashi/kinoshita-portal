#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches the current weekly feature (cover headline) for 5 business
magazines, so it's readable on the portal at a glance -- no click-through
needed. Each magazine has its own markup, so each gets its own small parser;
if one breaks (site redesign), that one magazine falls back to a plain
link rather than failing the whole fetch.

Diamond is the odd one out: diamond.jp's own backnumber page only shows
cover images, no text headline, so Fujisan's product page is used instead
(it prints the table-of-contents text, including the feature title).

Usage:
    python3 fetch_magazine_features.py magazine_features.json
"""
import html
import json
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"
TIMEOUT = 20


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def nikkei():
    url = "https://business.nikkei.com/magazine/"
    text = fetch(url)
    title = clean(re.search(r'l-localNavi_magazine_title">(.*?)</p>', text, re.S).group(1))
    issue = clean(re.search(r'l-localNavi_magazine_number">(.*?)</p>', text, re.S).group(1))
    return {"name": "日経ビジネス", "title": title, "issue": issue, "link": url}


def toyokeizai():
    url = "https://toyokeizai.net/list/magazine"
    text = fetch(url)
    m = re.search(
        r'magazine-list__subtitle">(.*?)</span>.*?'
        r'magazine-list__title">(.*?)</div>.*?'
        r'magazine-list__pubdate">(.*?)</span>',
        text, re.S,
    )
    subtitle, title, issue = m.groups()
    full_title = clean(title) + "　" + clean(subtitle)
    return {"name": "週刊東洋経済", "title": full_title, "issue": clean(issue), "link": url}


def diamond():
    url = "https://www.fujisan.co.jp/product/5771/new/"
    text = fetch(url)
    title = clean(re.search(r'特集1<br\s*/?>(.*?)<br\s*/?>', text, re.S).group(1))
    m_issue = re.search(r'(\d{4}年[\d・/]+号)', text)
    issue = m_issue.group(1) if m_issue else ""
    return {"name": "週刊ダイヤモンド", "title": title, "issue": issue, "link": "https://diamond.jp/list/dw"}


def economist():
    url = "https://www.weekly-economist.com/backnumber/"
    text = fetch(url)
    m = re.search(
        r'<div class="item">\s*<div class="magazine-information">\s*'
        r'<span class="update">(.*?)</span>.*?'
        r'<span class="header">(.*?)</span>\s*'
        r'<a href="([^"]+)"',
        text, re.S,
    )
    update, header, link = m.groups()
    y, mo, d = update.split(".")
    issue = f"{y}年{int(mo)}月{int(d)}日号"
    return {"name": "週刊エコノミスト", "title": clean(header), "issue": issue, "link": link}


def president():
    url = "https://president.jp/list/media/president"
    text = fetch(url)
    m = re.search(
        r'm-backnumber-item">.*?alt="([^"]+)".*?'
        r'm-backnumber-item__number">(.*?)</div>',
        text, re.S,
    )
    title, issue = m.groups()
    return {"name": "プレジデント", "title": clean(title), "issue": clean(issue), "link": url}


SOURCES = [
    ("日経ビジネス", nikkei, "https://business.nikkei.com/magazine/"),
    ("週刊東洋経済", toyokeizai, "https://toyokeizai.net/list/magazine"),
    ("週刊ダイヤモンド", diamond, "https://diamond.jp/list/dw"),
    ("週刊エコノミスト", economist, "https://www.weekly-economist.com/backnumber/"),
    ("プレジデント", president, "https://president.jp/list/media/president"),
]


def main(out_path):
    items = []
    errors = []
    for name, fn, fallback_url in SOURCES:
        try:
            items.append(fn())
        except Exception as e:
            errors.append(f"{name}: {e}")
            items.append({"name": name, "title": None, "issue": None, "link": fallback_url})

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False, indent=2)

    if errors:
        print("WARN: " + " / ".join(errors), file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_magazine_features.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

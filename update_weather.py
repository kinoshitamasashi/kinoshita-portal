#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Splices fetched weather data (weather_data.json, from fetch_weather.py)
into the weather widget in index.html.

Usage:
    python3 update_weather.py index.html weather_data.json
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from html import escape

JST = timezone(timedelta(hours=9))


def replace_tag(html, tag, class_name, new_inner):
    pattern = re.compile(
        r'(<' + tag + r' class="' + re.escape(class_name) + r'"[^>]*>)(.*?)(</' + tag + r'>)',
        re.S,
    )
    m = pattern.search(html)
    if not m:
        raise RuntimeError(f"{tag}.{class_name} not found")
    return html[:m.start()] + m.group(1) + new_inner + m.group(3) + html[m.end():]


def main(html_path, data_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    with open(data_path, 'r', encoding='utf-8-sig') as f:
        d = json.load(f)

    fetched = datetime.now(timezone.utc).astimezone(JST).strftime("%m/%d")

    html = replace_tag(html, "span", "weather-icon", d["today_icon"])
    html = replace_tag(html, "span", "weather-temp", f'{d["today_max"]}℃')
    html = replace_tag(html, "span", "weather-fetched mono", f"取得: {fetched}")
    html = replace_tag(html, "div", "weather-desc", escape(d["today_desc"]))
    range_text = (
        f'今日 {d["today_min"]}℃/{d["today_max"]}℃　'
        f'明日 {d["tomorrow_min"]}℃/{d["tomorrow_max"]}℃・{escape(d["tomorrow_desc"])}'
    )
    html = replace_tag(html, "div", "weather-range mono", range_text)

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("DONE", file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 update_weather.py <index.html> <weather_data.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

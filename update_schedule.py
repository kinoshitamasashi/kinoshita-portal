#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Splices fetched calendar events (schedule_data.json, from fetch_calendar.py)
into the "今週の予定" section of index.html.

Usage:
    python3 update_schedule.py index.html schedule_data.json
"""
import json
import re
import sys
from datetime import date, datetime
from html import escape

DOW_JP = ['月', '火', '水', '木', '金', '土', '日']


def parse_dt(s, all_day):
    if all_day:
        return date.fromisoformat(s)
    return datetime.fromisoformat(s)


def fmt_time_range(start, end, all_day):
    if all_day:
        if start == end:
            return "終日"
        return f"{start.month}/{start.day} 〜 {end.month}/{end.day} (終日)"

    same_day = start.date() == end.date()
    if same_day:
        if start == end:
            return f"{start.hour}:{start.minute:02d}"
        return f"{start.hour}:{start.minute:02d}–{end.hour}:{end.minute:02d}"

    dow_s = DOW_JP[start.weekday()]
    dow_e = DOW_JP[end.weekday()]
    return (f"{start.month}/{start.day}({dow_s}) {start.hour}:{start.minute:02d} 〜 "
            f"{end.month}/{end.day}({dow_e}) {end.hour}:{end.minute:02d}")


def build_rows(items):
    rows = []
    for it in items:
        start = parse_dt(it["start"], it["all_day"])
        end = parse_dt(it["end"], it["all_day"])
        day_num = start.day
        dow = DOW_JP[start.weekday()]
        title = escape(it["title"])
        time_str = fmt_time_range(start, end, it["all_day"])
        href = f"https://calendar.google.com/calendar/u/0/r/day/{start.year}/{start.month:02d}/{start.day:02d}"
        rows.append(
            f'        <a class="sched-row" target="_blank" rel="noopener noreferrer" href="{href}">\n'
            f'          <span class="sched-date"><span class="sched-day">{day_num}</span><span class="sched-dow">{dow}</span></span>\n'
            f'          <span class="sched-info">\n'
            f'            <span class="sched-title">{title}</span>\n'
            f'            <span class="sched-time mono">{time_str}</span>\n'
            f'          </span>\n'
            f'        </a>\n'
        )
    if not rows:
        rows.append(
            '        <div class="sched-empty">今週の予定はありません</div>\n'
        )
    return ''.join(rows)


def main(html_path, data_path):
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    with open(data_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    today = date.fromisoformat(data["today"])
    range_end = date.fromisoformat(data["range_end"])
    date_range_str = f"{today.month}/{today.day}-{range_end.month}/{range_end.day}"

    m = re.search(r'<div class="schedule-title">.*?<span class="cat-count mono">[^<]*</span>', html, re.S)
    if not m:
        raise RuntimeError("schedule-title block not found")
    new_title_block = re.sub(
        r'(<span class="cat-count mono">)[^<]*(</span>)',
        rf'\g<1>{date_range_str}\g<2>',
        m.group(0)
    )
    html = html[:m.start()] + new_title_block + html[m.end():]

    list_open = '<div class="schedule-list">'
    list_idx = html.find(list_open)
    if list_idx < 0:
        raise RuntimeError("schedule-list block not found")
    list_open_end = list_idx + len(list_open)

    depth = 1
    close_end = -1
    for mm in re.finditer(r'<div\b|</div>', html[list_open_end:]):
        if mm.group() == '</div>':
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            close_end = list_open_end + mm.end()
            break
    if close_end < 0:
        raise RuntimeError("matching close div not found for schedule-list")
    close_start = close_end - len('</div>')

    rows = build_rows(data["items"])
    html = html[:list_open_end] + '\n' + rows + '      ' + html[close_start:]

    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print("DONE", file=sys.stderr)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python3 update_schedule.py <index.html> <schedule_data.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])

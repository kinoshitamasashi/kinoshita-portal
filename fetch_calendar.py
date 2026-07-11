#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches events for the next 7 days from a Google Calendar private iCal URL
(CALENDAR_ICS_URL env var) and writes them as JSON.

Usage:
    python3 fetch_calendar.py schedule_data.json
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta

import icalendar
import recurring_ical_events


def main(out_path):
    url = os.environ.get("CALENDAR_ICS_URL")
    if not url:
        print("CALENDAR_ICS_URL is not set", file=sys.stderr)
        sys.exit(1)

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    cal = icalendar.Calendar.from_ical(raw)

    today = date.today()
    range_end = today + timedelta(days=6)
    occurrences = recurring_ical_events.of(cal).between(today, range_end + timedelta(days=1))

    items = []
    for ev in occurrences:
        summary = str(ev.get("summary", "(無題)"))
        dtstart = ev["dtstart"].dt
        dtend_prop = ev.get("dtend")
        dtend = dtend_prop.dt if dtend_prop else dtstart
        all_day = not isinstance(dtstart, datetime)

        if all_day and isinstance(dtend, date) and dtend > dtstart:
            dtend = dtend - timedelta(days=1)

        items.append({
            "title": summary,
            "start": dtstart.isoformat(),
            "end": dtend.isoformat(),
            "all_day": all_day,
        })

    items.sort(key=lambda x: x["start"])
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "today": today.isoformat(),
            "range_end": range_end.isoformat(),
            "items": items,
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_calendar.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches weather for Kobe (神戸市西区) from two free, keyless sources:
- JMA (Japan Meteorological Agency) for the Japanese weather description text
- Open-Meteo for clean, unambiguous daily min/max temperatures

Usage:
    python3 fetch_weather.py weather_data.json
"""
import json
import re
import sys
import urllib.request

UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"
JMA_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/280000.json"
OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude=34.75&longitude=135.00"
    "&daily=temperature_2m_max,temperature_2m_min&timezone=Asia%2FTokyo&forecast_days=2"
)
KOBE_AREA_CODE = "280010"  # 兵庫県南部（神戸を含む）

WEATHER_CODE = {
    "100": "晴れ", "101": "晴れ時々くもり", "102": "晴れ一時雨", "103": "晴れ時々雨",
    "104": "晴れ一時雪", "105": "晴れ時々雪", "110": "晴れのち時々くもり", "111": "晴れのちくもり",
    "112": "晴れのち一時雨", "113": "晴れのち時々雨", "114": "晴れのち雨", "119": "晴れのち雷雨",
    "123": "晴れ山沿い雷雨", "125": "晴れ夕方雷雨", "126": "晴れ昼頃雷雨",
    "140": "晴れ時々雨で雷を伴う", "160": "晴れ一時雪か雨", "170": "晴れ時々雪か雨",
    "181": "晴れのち雪か雨",
    "200": "くもり", "201": "くもり時々晴れ", "202": "くもり一時雨", "203": "くもり時々雨",
    "204": "くもり一時雪", "205": "くもり時々雪", "206": "くもり一時雨か雪",
    "209": "霧", "210": "くもりのち時々晴れ", "211": "くもりのち晴れ", "212": "くもりのち一時雨",
    "213": "くもりのち時々雨", "214": "くもりのち雨", "215": "くもりのち一時雪",
    "216": "くもりのち時々雪", "217": "くもりのち雪", "224": "くもり一時雨後晴れ",
    "231": "くもり海上海岸で霧か霧雨", "240": "くもり時々雨で雷を伴う",
    "250": "くもり時々雪で雷を伴う", "260": "くもり一時雪か雨", "270": "くもり時々雪か雨",
    "281": "くもりのち雪か雨",
    "300": "雨", "301": "雨時々晴れ", "302": "雨時々止む", "303": "雨時々雪",
    "308": "雨で暴風を伴う", "311": "雨のち晴れ", "313": "雨のちくもり",
    "314": "雨のち時々雪", "315": "雨のち雪", "320": "朝の内雨のち晴れ",
    "321": "朝の内雨のちくもり", "322": "夕方から雨", "323": "夜のはじめ頃から雨",
    "325": "夜半から雨", "328": "顕著な大雨", "329": "雷を伴い雨",
    "340": "雪か雨", "350": "雷を伴う",
    "400": "雪", "401": "雪時々晴れ", "402": "雪時々止む", "403": "雪時々雨",
    "405": "大雪", "406": "風雪強い", "407": "暴風雪", "411": "雪のち晴れ",
    "413": "雪のちくもり", "414": "雪のち雨", "425": "雷を伴い雪", "430": "雪一時雨",
    "450": "雷を伴う",
}

THUNDER_CODES = {"350", "308", "329", "425", "406", "407", "140", "240", "250"}


def short_weather(code, fallback_text):
    if code in WEATHER_CODE:
        return WEATHER_CODE[code]
    cleaned = re.sub(r'[　\s]+', '', fallback_text or "")
    return cleaned[:12] if cleaned else "不明"


def icon_for_code(code):
    if not code:
        return "❓"
    if code in THUNDER_CODES:
        return "⛈️"
    head = code[0]
    if head == "1":
        return "☀️" if code == "100" else "\U0001f324️"
    if head == "2":
        return "☁️"
    if head == "3":
        return "\U0001f327️"
    if head == "4":
        return "❄️"
    return "\U0001f321️"


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def main(out_path):
    jma = fetch_json(JMA_URL)
    areas = jma[0]["timeSeries"][0]["areas"]
    kobe = next(a for a in areas if a["area"]["code"] == KOBE_AREA_CODE)
    today_code = kobe["weatherCodes"][0]
    tomorrow_code = kobe["weatherCodes"][1]
    today_text = kobe["weathers"][0]
    tomorrow_text = kobe["weathers"][1]

    om = fetch_json(OPEN_METEO_URL)
    daily = om["daily"]
    today_min = round(daily["temperature_2m_min"][0])
    today_max = round(daily["temperature_2m_max"][0])
    tomorrow_min = round(daily["temperature_2m_min"][1])
    tomorrow_max = round(daily["temperature_2m_max"][1])

    result = {
        "today_icon": icon_for_code(today_code),
        "today_desc": short_weather(today_code, today_text),
        "today_min": today_min,
        "today_max": today_max,
        "tomorrow_desc": short_weather(tomorrow_code, tomorrow_text),
        "tomorrow_min": tomorrow_min,
        "tomorrow_max": tomorrow_max,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_weather.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

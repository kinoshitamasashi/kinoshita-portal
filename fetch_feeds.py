#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetches the curated RSS/RDF feeds directly over HTTP and writes feed_data.json
in the shape update_news.py expects. Meant to run in an environment with real
outbound network access (e.g. GitHub Actions), not the CCR cloud sandbox.

Usage:
    python3 fetch_feeds.py feed_data.json
"""
import difflib
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

SIMILARITY_THRESHOLD = 0.85
DUP_WINDOW_DAYS = 1


def normalize_title(title):
    # strip trailing attribution/page markers like "（デイリー新潮）" or "(2ページ目)"
    return re.sub(r'[（(][^（）()]{1,20}[）)]\s*$', '', title).strip()


def is_near_duplicate(a, b):
    return difflib.SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= SIMILARITY_THRESHOLD


MAX_PER_ENTITY_CLUSTER = 2


def extract_entity_tokens(title):
    # Distinctive proper-noun-ish tokens (brand names etc.), used to cap how many
    # articles about the same single event (same day, same named entity) pile up.
    return set(re.findall(r'[ァ-ヴー]{4,}', title))


def shares_entity(a_tokens, b_tokens):
    return bool(a_tokens & b_tokens)


# Sources known to commonly paywall full articles (best-effort heuristic;
# RSS metadata doesn't expose per-article paywall status).
PAYWALLED_SOURCES = {
    "日本経済新聞", "日経電子版", "日経ビジネス", "日経ビジネス電子版",
    "日経クロステック", "日経xTECH", "Bloomberg", "ウォール・ストリート・ジャーナル", "WSJ",
}


def is_paywalled(source):
    return source in PAYWALLED_SOURCES


# Press-release distribution services: anyone can pay to publish here, so these
# are not an editor's judgment of importance. Deprioritized, not excluded.
PRESS_RELEASE_SOURCES = {
    "PR TIMES", "@Press", "アットプレス", "Digital PR Platform", "value press",
    "バリュープレス", "共同通信PRワイヤー", "ValuePress!", "PRWire",
}


def is_press_release(source):
    return source in PRESS_RELEASE_SOURCES


UA = "Mozilla/5.0 (compatible; KinoshitaPortalBot/1.0)"

IH_QUERY = "IHクッキングヒーター OR 電磁調理器 OR IHコンロ OR IH調理器"
IOT_QUERY = "IoT家電 OR スマート家電 OR コネクテッド家電 OR スマートキッチン"
HOUSING_EQUIPMENT_QUERY = "住宅設備 OR 工事専門店"
KITCHEN_QUERY = "システムキッチン OR Miele OR タカラスタンダード OR クリナップ"
AI_QUERY = "ChatGPT OR Claude OR Copilot"
FOODTECH_QUERY = "フードテック OR 自動調理 OR 調理家電"
# Google News matches full article text, not just the title, so a brand name
# or phrase can surface an unrelated local/civic story that merely mentions it
# in passing (e.g. a factory host city's youth contest announcement). Exclude
# the recognizable noise pattern rather than chase each one individually.
BIGNEWS_NOISE_EXCLUDE = "-コンテスト -児童 -青少年"

BIGNEWS_QUERY = (
    "(家電メーカー OR 住宅メーカー OR キッチンメーカー OR 家電量販店 OR 住宅設備 OR IHクッキングヒーター) "
    "(買収 OR 経営統合 OR 合併 OR 資本提携) " + BIGNEWS_NOISE_EXCLUDE
)
BIGNEWS_GLOBAL_QUERY = (
    "(Samsung OR LG電子 OR Whirlpool OR Electrolux OR Haier OR ハイアール OR Midea OR 美的 OR GEアプライアンス) "
    "(家電 OR 住宅設備 OR 白物家電) "
    "(買収 OR 経営統合 OR 合併 OR M&A) " + BIGNEWS_NOISE_EXCLUDE
)
BIGNEWS_TECH_QUERY = (
    "(家電 OR IHクッキングヒーター OR キッチン家電 OR 住宅設備 OR 省エネ住宅) "
    "(技術革新 OR 新技術開発 OR ブレークスルー) " + BIGNEWS_NOISE_EXCLUDE
)
BIGNEWS_ENTRY_QUERY = (
    "(住宅設備メーカー OR 家電メーカー OR キッチンメーカー) "
    "(日本上陸 OR 日本進出 OR 日本市場参入 OR 日本初出店) " + BIGNEWS_NOISE_EXCLUDE
)
TOC_QUERY = "制約理論 OR ゴールドラット OR スループット会計 OR 制約条件理論"
BIZBOOK_QUERY = "ビジネス書 (ランキング OR ベストセラー OR 書評) -俳優 -女優 -アイドル"
RETAIL_QUERY = "家電量販店 (新業態 OR ビジネスモデル OR 新事業 OR 事業変革)"
POLICY_QUERY = (
    "(家電 OR 住宅 OR 省エネ住宅) "
    "(経済産業省 OR 国土交通省 OR 省エネ法 OR 建築物省エネ法 OR トップランナー制度)"
)
LOCAL_NEWS_QUERY = "site:kobe-np.co.jp (明石 OR 神戸市)"

# 神戸新聞 covers everything from routine crime blotter to high school baseball;
# only items whose title itself signals a genuinely large-scale/administrative
# or life-affecting story are kept (store-opening info comes from the two
# local "journal" sites instead, which need no such filter).
KOBE_SHIMBUN_IMPACT_KEYWORDS = [
    "停電", "断水", "運休", "通行止め", "避難指示", "避難勧告", "警報",
    "補助金", "値上げ", "料金改定",
    "感染症", "インフルエンザ", "台風", "地震", "豪雨", "浸水",
    "新設", "移転", "上場",
    "給与", "条例改正", "制度変更", "就航", "開設",
]


def is_life_impact(title):
    return any(k in title for k in KOBE_SHIMBUN_IMPACT_KEYWORDS)


# User lives in Kobe's Nishi ward; store-opening posts (明石じゃーなる /
# 神戸ジャーナル cover all of Hyogo) about wards too far from home are
# dropped: east of Chuo, plus Kita (北区).
TOO_FAR_WARDS = ["東灘区", "灘区", "北区"]


def is_too_far_east(title):
    return any(w in title for w in TOO_FAR_WARDS)


def gnews(query):
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote(query) + "&hl=ja&gl=JP&ceid=JP:ja"


FEEDS = [
    {"url": "https://kaden.watch.impress.co.jp/data/rss/1.0/kdw/feed.rdf", "source": "家電Watch", "cat": "appliance"},
    {"url": "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml", "source": "ITmedia AI+", "cat": "ai"},
    {"url": "https://foodtech-japan.com/feed/", "source": "Foovo", "cat": "food"},
    {"url": "https://www.housenews.jp/feed", "source": "住宅産業新聞", "cat": "food"},
    {"url": "https://toyokeizai.net/list/feed/rss", "source": "東洋経済オンライン", "cat": "magazine"},
    {"url": "https://diamond.jp/list/feed/rss/dol", "source": "ダイヤモンド・オンライン", "cat": "magazine"},
    {"url": "https://gekirock.com/news/index.xml", "source": "激ロック", "cat": "rock"},
    {"url": gnews(IH_QUERY), "source": None, "cat": "ih_focus"},
    {"url": gnews(IOT_QUERY), "source": None, "cat": "ih_focus"},
    {"url": gnews(HOUSING_EQUIPMENT_QUERY), "source": None, "cat": "ih_focus"},
    {"url": gnews(KITCHEN_QUERY), "source": None, "cat": "food"},
    {"url": gnews(AI_QUERY), "source": None, "cat": "ai"},
    {"url": gnews(FOODTECH_QUERY), "source": None, "cat": "food"},
    {"url": gnews(BIGNEWS_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(BIGNEWS_GLOBAL_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(BIGNEWS_TECH_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(BIGNEWS_ENTRY_QUERY), "source": None, "cat": "big_news"},
    {"url": gnews(TOC_QUERY), "source": None, "cat": "toc", "subcat": "core"},
    {"url": gnews(BIZBOOK_QUERY), "source": None, "cat": "toc", "subcat": "book"},
    {"url": gnews(RETAIL_QUERY), "source": None, "cat": "appliance"},
    {"url": gnews(POLICY_QUERY), "source": None, "cat": "policy"},
    {"url": gnews(LOCAL_NEWS_QUERY), "source": None, "cat": "local_news", "subcat": "kobe_shimbun"},
    {"url": "https://akashi-journal.com/category/openclose/feed/", "source": "明石じゃーなる", "cat": "local_news", "subcat": "journal"},
    {"url": "https://kobe-journal.com/archives/tag/%E9%96%8B%E5%BA%97%EF%BC%8F%E3%82%AA%E3%83%BC%E3%83%97%E3%83%B3/feed/", "source": "神戸ジャーナル", "cat": "local_news", "subcat": "journal"},
]

TOP_N = {"appliance": 22, "ai": 8, "magazine": 18, "food": 15, "rock": 15, "ih_focus": 20, "big_news": 35, "toc": 15, "policy": 15, "local_news": 18}

# Some categories blend subtopics with very different publish frequency (a
# plain recency sort lets the frequent one crowd the rare one out entirely),
# so those reserve floor slots per subtopic instead of trimming the merged
# pool as one list. "toc": TOC articles are rare, business-book roundups are
# weekly. "local_news": journal store-opening posts are frequent, genuinely
# big Kobe Shimbun stories are rare.
SUBCAT_RESERVED = {
    "toc": {"core": 6, "book": 6},
    "local_news": {"journal": 8, "kobe_shimbun": 6},
}


def apply_subcat_reservation(deduped, reserved, top_n):
    order = {id(it): i for i, it in enumerate(deduped)}
    selected = []
    for subcat, floor in reserved.items():
        bucket = [it for it in deduped if it.get("_subcat") == subcat]
        selected += bucket[:floor]
    remaining = top_n - len(selected)
    if remaining > 0:
        selected_ids = {id(it) for it in selected}
        leftover = [it for it in deduped if id(it) not in selected_ids]
        selected += leftover[:remaining]
    selected.sort(key=lambda x: order[id(x)])
    return selected


def local_name(tag):
    return tag.split('}')[-1]


def parse_date(item):
    for child in item:
        name = local_name(child.tag)
        text = (child.text or "").strip()
        if not text:
            continue
        if name == "pubDate":
            try:
                dt = parsedate_to_datetime(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                continue
        if name == "date":
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                continue
    return None


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return ET.fromstring(raw)


def extract_items(root):
    items = []
    for el in root.iter():
        if local_name(el.tag) == "item":
            items.append(el)
    return items


def item_fields(item):
    title, link, source = None, None, None
    for child in item:
        name = local_name(child.tag)
        if name == "title" and title is None:
            title = (child.text or "").strip()
        elif name == "link" and link is None:
            link = (child.text or "").strip()
        elif name == "source" and source is None:
            source = (child.text or "").strip()
    if title and source:
        title = re.sub(r'\s*-\s*' + re.escape(source) + r'$', '', title).strip()
    return title, link, source


def main(out_path):
    result = {"appliance": [], "ai": [], "magazine": [], "food": [], "rock": [], "ih_focus": [], "big_news": [], "toc": [], "policy": [], "local_news": []}
    errors = []

    for feed in FEEDS:
        try:
            root = fetch_feed(feed["url"])
            items = extract_items(root)
            for item in items:
                title, link, item_source = item_fields(item)
                dt = parse_date(item)
                source = feed["source"] or item_source
                if not title or not link or dt is None or not source:
                    continue
                if feed.get("subcat") == "kobe_shimbun" and not is_life_impact(title):
                    continue
                if feed.get("subcat") == "journal" and is_too_far_east(title):
                    continue
                result[feed["cat"]].append({
                    "title": title,
                    "link": link,
                    "date": dt.strftime("%Y-%m-%d"),
                    "source": source,
                    "_sort": dt,
                    "_subcat": feed.get("subcat"),
                })
        except Exception as e:
            errors.append(f"{feed['source'] or feed['cat']} ({feed['url']}): {e}")

    for cat in result:
        result[cat].sort(key=lambda x: x["_sort"], reverse=True)
        deduped = []
        for it in result[cat]:
            del it["_sort"]
            it_date = datetime.strptime(it["date"], "%Y-%m-%d").date()
            dup_index = None
            for idx, kept in enumerate(deduped):
                kept_date = datetime.strptime(kept["date"], "%Y-%m-%d").date()
                if abs((it_date - kept_date).days) <= DUP_WINDOW_DAYS and is_near_duplicate(it["title"], kept["title"]):
                    dup_index = idx
                    break
            if dup_index is not None:
                kept = deduped[dup_index]
                if is_paywalled(kept["source"]) and not is_paywalled(it["source"]):
                    deduped[dup_index] = it
                continue

            # cap how many articles about the same single event (same brand-name
            # token, same narrow date window) can pile up from heavy syndication
            it_tokens = extract_entity_tokens(it["title"])
            if it_tokens:
                cluster_count = 0
                for kept in deduped:
                    kept_date = datetime.strptime(kept["date"], "%Y-%m-%d").date()
                    if abs((it_date - kept_date).days) <= DUP_WINDOW_DAYS and shares_entity(it_tokens, extract_entity_tokens(kept["title"])):
                        cluster_count += 1
                if cluster_count >= MAX_PER_ENTITY_CLUSTER:
                    continue

            deduped.append(it)

        # prefer independently-reported items over paid press-release wire
        # copy when trimming to the display cap (recency order is preserved
        # within each tier since sort() is stable)
        deduped.sort(key=lambda x: is_press_release(x["source"]))

        if cat in SUBCAT_RESERVED:
            result[cat] = apply_subcat_reservation(deduped, SUBCAT_RESERVED[cat], TOP_N[cat])
        else:
            result[cat] = deduped[:TOP_N[cat]]

        for it in result[cat]:
            it.pop("_subcat", None)

        if not result[cat]:
            errors.append(f"category '{cat}' ended up empty")

    if errors:
        print("WARNINGS:\n" + "\n".join(errors), file=sys.stderr)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    if all(not result[cat] for cat in result):
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 fetch_feeds.py <out.json>", file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

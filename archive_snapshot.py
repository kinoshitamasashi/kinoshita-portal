import os
import re
import sys
from datetime import datetime, timedelta, timezone

RETENTION_DAYS = 7
JST = timezone(timedelta(hours=9))

INDEX_LISTING_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>バックナンバー - 木下ポータル</title>
<style>
  :root {{
    --bg: #F6F4EF;
    --surface: #FFFFFF;
    --ink: #1E2126;
    --ink-soft: #55606B;
    --heat: #C85A26;
    --border: #DCD8CE;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #14161C;
      --surface: #1C1F27;
      --ink: #ECEAE4;
      --ink-soft: #9AA3AE;
      --heat: #FF8A4C;
      --border: #2E323D;
    }}
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    padding: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: "Noto Sans JP", "Hiragino Kaku Gothic ProN", "Yu Gothic UI", "Meiryo", system-ui, sans-serif;
  }}
  .wrap {{
    max-width: 640px;
    margin: 0 auto;
    padding: 24px 20px 48px;
  }}
  h1 {{
    font-size: 1.3rem;
    margin: 0 0 4px;
  }}
  p.lead {{
    color: var(--ink-soft);
    font-size: 0.85rem;
    margin: 0 0 20px;
  }}
  ul {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  li a {{
    display: block;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 4px solid var(--heat);
    border-radius: 10px;
    padding: 14px 16px;
    color: var(--ink);
    text-decoration: none;
    font-size: 0.95rem;
  }}
  li a:hover {{
    border-left-width: 6px;
  }}
  .back {{
    display: inline-block;
    margin-top: 28px;
    color: var(--ink-soft);
    text-decoration: none;
    font-size: 0.85rem;
  }}
  .empty {{
    color: var(--ink-soft);
    font-size: 0.9rem;
  }}
</style>
</head>
<body>
<div class="wrap">
  <h1>バックナンバー</h1>
  <p class="lead">過去{days}日分のニュース・スナップショットを保存しています。</p>
  {body}
  <a class="back" href="../index.html">‹ 木下ポータルに戻る</a>
</div>
</body>
</html>
"""


def jst_today():
    return datetime.now(JST).date()


def snapshot(index_path, archive_dir):
    today = jst_today()
    os.makedirs(archive_dir, exist_ok=True)

    with open(index_path, encoding="utf-8") as f:
        html = f.read()

    today_file = os.path.join(archive_dir, f"{today.isoformat()}.html")
    with open(today_file, "w", encoding="utf-8") as f:
        f.write(html)

    cutoff = today - timedelta(days=RETENTION_DAYS)
    date_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")
    kept_dates = []
    for name in os.listdir(archive_dir):
        m = date_pattern.match(name)
        if not m:
            continue
        file_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
        if file_date < cutoff:
            os.remove(os.path.join(archive_dir, name))
        else:
            kept_dates.append(file_date)

    kept_dates.sort(reverse=True)

    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    if kept_dates:
        items = []
        for d in kept_dates:
            label = f"{d.month}月{d.day}日（{weekdays[d.weekday()]}）"
            items.append(f'    <li><a href="{d.isoformat()}.html">{label}</a></li>')
        body = "<ul>\n" + "\n".join(items) + "\n  </ul>"
    else:
        body = '<p class="empty">まだバックナンバーがありません。</p>'

    listing_html = INDEX_LISTING_TEMPLATE.format(days=RETENTION_DAYS, body=body)
    with open(os.path.join(archive_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(listing_html)

    print(f"Saved snapshot {today_file}, {len(kept_dates)} kept.")


if __name__ == "__main__":
    index_path = sys.argv[1]
    archive_dir = sys.argv[2]
    snapshot(index_path, archive_dir)

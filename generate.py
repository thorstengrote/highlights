#!/usr/bin/env python3
"""Fetches Sportschau highlights and generates index.html."""

import urllib.request
import re
import json
import sys
from html import unescape
from datetime import datetime, timezone

LIST_URL = "https://www.sportschau.de/thema/highlights"


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_date(iso):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else ""


def extract_list(html):
    html_u = unescape(html)
    date_by_url = {}
    for m in re.finditer(r'"broadcastedOnDateTime":"([^"]+)"', html_u):
        after = html_u[m.start() : m.start() + 600]
        link_m = re.search(r'"link":"(https://www\.sportschau\.de[^"]+)"', after)
        if link_m:
            date_by_url[link_m.group(1)] = parse_date(m.group(1))

    results = []
    seen = set()
    for href, inner in re.findall(
        r'<a\s[^>]*href="(/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE
    ):
        heading = re.search(
            r"<h[1-6][^>]*>(.*?)</h[1-6]>", inner, re.DOTALL | re.IGNORECASE
        )
        if not heading:
            continue
        title = re.sub(r"<[^>]+>", "", heading.group(1)).strip()
        title = re.sub(r"\s+", " ", title)
        if not title or href in seen:
            continue
        seen.add(href)
        full_url = "https://www.sportschau.de" + href
        results.append((title, full_url, date_by_url.get(full_url, "")))
    return results


def extract_video_url(page_url):
    try:
        html = fetch(page_url)
        for j in re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        ):
            try:
                d = json.loads(j)
                for item in d if isinstance(d, list) else [d]:
                    if item.get("@type") == "VideoObject" and "contentUrl" in item:
                        return item["contentUrl"]
            except Exception:
                pass
    except Exception as e:
        print(f"  Fehler bei {page_url}: {e}", file=sys.stderr)
    return None


def generate_html(items, updated_at):
    rows = []
    for i, (title, page_url, date, video_url) in enumerate(items, 1):
        if video_url:
            link = f'<a href="{video_url}" target="_blank" rel="noopener">{title}</a>'
        else:
            link = f'<span class="no-video">{title}</span>'
        date_cell = f'<td class="date">{date}</td>' if date else '<td class="date"></td>'
        rows.append(f"<tr><td class='num'>{i}</td>{date_cell}<td>{link}</td></tr>")

    rows_html = "\n        ".join(rows)
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Sportschau Highlights</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f0f0f;
      color: #e0e0e0;
      padding: 2rem 1rem;
      max-width: 720px;
      margin: 0 auto;
    }}
    h1 {{
      font-size: 1.4rem;
      font-weight: 600;
      margin-bottom: 0.4rem;
      color: #fff;
    }}
    .updated {{
      font-size: 0.78rem;
      color: #666;
      margin-bottom: 2rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    tr + tr {{ border-top: 1px solid #1e1e1e; }}
    td {{
      padding: 0.75rem 0.5rem;
      vertical-align: middle;
    }}
    td.num {{
      color: #555;
      font-size: 0.85rem;
      width: 2rem;
      text-align: right;
      padding-right: 1rem;
    }}
    td.date {{
      color: #888;
      font-size: 0.82rem;
      white-space: nowrap;
      width: 7rem;
    }}
    a {{
      color: #e0e0e0;
      text-decoration: none;
      font-size: 0.95rem;
      line-height: 1.4;
    }}
    a:hover {{ color: #fff; text-decoration: underline; }}
    .no-video {{ color: #555; font-size: 0.95rem; }}
    @media (max-width: 480px) {{
      td.date {{ display: none; }}
    }}
  </style>
</head>
<body>
  <h1>Sportschau Highlights</h1>
  <p class="updated">Aktualisiert: {updated_at}</p>
  <table>
        {rows_html}
  </table>
</body>
</html>
"""


def main():
    print("Lade Highlights-Liste ...", file=sys.stderr)
    html = fetch(LIST_URL)
    items_raw = extract_list(html)
    print(f"{len(items_raw)} Einträge gefunden.", file=sys.stderr)

    items = []
    for i, (title, page_url, date) in enumerate(items_raw, 1):
        print(f"  [{i}/{len(items_raw)}] {title}", file=sys.stderr)
        video_url = extract_video_url(page_url)
        items.append((title, page_url, date, video_url))

    updated_at = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    html_out = generate_html(items, updated_at)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_out)
    print("index.html geschrieben.", file=sys.stderr)


if __name__ == "__main__":
    main()

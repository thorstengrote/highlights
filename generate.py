#!/usr/bin/env python3
"""Fetches Sportschau highlights and generates index.html."""

import urllib.request
import re
import json
import sys
from html import unescape
from datetime import datetime, timezone, timedelta

SOURCES = [
    "https://www.sportschau.de/thema/highlights",
    "https://www.sportschau.de/fussball/fifa-wm-2026/?typ=video",
]

CEST = timezone(timedelta(hours=2))


def fetch(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_iso(raw):
    """Return ISO datetime string normalized to UTC, or '' on failure."""
    if not raw:
        return ""
    # Handle +0000 / +00:00 / Z suffixes
    raw = re.sub(r"\+0000$", "+00:00", raw.strip())
    raw = re.sub(r"Z$", "+00:00", raw)
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00+00:00" if m else ""


def format_datetime(iso):
    """'2026-06-16T01:00:00+00:00' → '16.06. 03:00' (CEST)"""
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso).astimezone(CEST)
        return dt.strftime("%d.%m.&thinsp;%H:%M")
    except Exception:
        return ""


EXCLUDE = ["paralympics"]


def is_highlight(title, href):
    t = title.lower()
    h = href.lower()
    if any(x in t or x in h for x in EXCLUDE):
        return False
    return "highlight" in t or "highlight" in h


def extract_items(html):
    html_u = unescape(html)
    iso_by_url = {}
    for m in re.finditer(r'"broadcastedOnDateTime":"([^"]+)"', html_u):
        after = html_u[m.start() : m.start() + 600]
        link_m = re.search(r'"link":"(https://www\.sportschau\.de[^"]+)"', after)
        if link_m:
            iso_by_url[link_m.group(1)] = parse_iso(m.group(1))

    results = {}
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
        if not title or not is_highlight(title, href):
            continue
        key = re.sub(r",[\w-]+\.html$", "", href)
        full_url = "https://www.sportschau.de" + href
        if key not in results:
            results[key] = (title, full_url, iso_by_url.get(full_url, ""))
    return results


def extract_video_and_iso(page_url):
    """Returns (video_url, iso_str) — either may be None."""
    video_url = None
    iso_str = None
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
                    if item.get("@type") == "VideoObject":
                        if not video_url and "contentUrl" in item:
                            video_url = item["contentUrl"]
                        if not iso_str:
                            iso_str = parse_iso(item.get("datePublished") or item.get("dateModified"))
                    elif not iso_str and item.get("@type") in ("NewsArticle", "Article", "WebPage"):
                        iso_str = parse_iso(item.get("datePublished") or item.get("dateModified"))
            except Exception:
                pass
    except Exception as e:
        print(f"  Fehler bei {page_url}: {e}", file=sys.stderr)
    return video_url, iso_str


def generate_html(items, updated_at):
    rows = []
    for i, (title, page_url, iso, video_url) in enumerate(items, 1):
        if video_url:
            link = f'<a href="{video_url}" target="_blank" rel="noopener">{title}</a>'
        else:
            link = f'<span class="no-video">{title}</span>'
        display = format_datetime(iso)
        date_cell = f'<td class="date">{display}</td>'
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
      width: 6.5rem;
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
    merged = {}
    for url in SOURCES:
        print(f"Lade {url} ...", file=sys.stderr)
        html = fetch(url)
        items = extract_items(html)
        new = {k: v for k, v in items.items() if k not in merged}
        merged.update(new)
        print(f"  {len(items)} Highlights, {len(new)} neu. Gesamt: {len(merged)}", file=sys.stderr)

    print(f"\n{len(merged)} Einträge. Hole Video-URLs ...", file=sys.stderr)
    items = []
    for i, (title, page_url, iso) in enumerate(merged.values(), 1):
        print(f"  [{i}/{len(merged)}] {title}", file=sys.stderr)
        video_url, page_iso = extract_video_and_iso(page_url)
        if not iso and page_iso:
            iso = page_iso
        items.append((title, page_url, iso, video_url))

    # Neueste oben, undatierte ans Ende
    items.sort(key=lambda x: x[2] if x[2] else "0000", reverse=True)

    updated_at = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    html_out = generate_html(items, updated_at)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_out)
    print("index.html geschrieben.", file=sys.stderr)


if __name__ == "__main__":
    main()

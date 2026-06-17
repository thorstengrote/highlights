#!/usr/bin/env python3
"""Fetches Sportschau + MagentaSport highlights and generates index.html."""

import urllib.request
import re
import json
import sys
import subprocess
from html import unescape
from datetime import datetime, timezone, timedelta

# ---------- config ----------

SPORTSCHAU_SOURCES = [
    "https://www.sportschau.de/thema/highlights",
    "https://www.sportschau.de/fussball/fifa-wm-2026/?typ=video",
]
YT_CHANNEL = "https://www.youtube.com/@MAGENTASPORT"
YT_CHANNEL_ID = "UChr7ZXDFiPOEl543HM4Aj8g"
YT_WM_PLAYLIST = "https://www.youtube.com/playlist?list=PLSTUQ-Z10W594c6BwieXpQa1WtbhYSeIV"
YT_LIMIT = 100
CEST = timezone(timedelta(hours=2))

# ---------- team normalisation ----------

_NORM = {
    "neuseeland": "new zealand", "new zealand": "new zealand",
    "saudi-arabien": "saudi arabia", "saudi arabia": "saudi arabia",
    "kap verde": "cape verde", "cape verde": "cape verde", "cabo verde": "cape verde",
    "elfenbeinküste": "ivory coast", "elfenbeinkuste": "ivory coast", "ivory coast": "ivory coast",
    "côte d'ivoire": "ivory coast", "cote d'ivoire": "ivory coast",
    "bosnien und herzegowina": "bosnia", "bosnien": "bosnia",
    "bosnien-herzegowina": "bosnia",
    "bosnia and herzegovina": "bosnia", "bosnia": "bosnia",
    "tschechien": "czech republic", "czech republic": "czech republic",
    "südkorea": "south korea", "south korea": "south korea",
    "südafrika": "south africa", "south africa": "south africa",
    "ägypten": "egypt", "agypten": "egypt", "egypt": "egypt",
    "türkei": "turkey", "turkei": "turkey", "turkey": "turkey",
    "katar": "qatar", "qatar": "qatar",
    "schweiz": "switzerland", "switzerland": "switzerland",
    "niederlande": "netherlands", "netherlands": "netherlands",
    "schottland": "scotland", "scotland": "scotland",
    "marokko": "morocco", "morocco": "morocco",
    "norwegen": "norway", "norway": "norway",
    "algerien": "algeria", "algeria": "algeria",
    "tunesien": "tunisia", "tunisia": "tunisia",
    "schweden": "sweden", "sweden": "sweden",
    "belgien": "belgium", "belgium": "belgium",
    "frankreich": "france", "france": "france",
    "spanien": "spain", "spain": "spain",
    "brasilien": "brazil", "brazil": "brazil",
    "kanada": "canada", "canada": "canada",
    "mexiko": "mexico", "mexico": "mexico",
    "australien": "australia", "australia": "australia",
    "deutschland": "germany", "germany": "germany",
    "curaçao": "curacao", "curacao": "curacao",
    "argentinien": "argentina", "argentina": "argentina",
    "vereinigte staaten": "usa", "usa": "usa",
    "haiti": "haiti", "irak": "iraq", "iraq": "iraq",
    "iran": "iran", "japan": "japan", "portugal": "portugal",
    "england": "england", "kroatien": "croatia", "croatia": "croatia",
    "serbien": "serbia", "serbia": "serbia",
    "österreich": "austria", "osterreich": "austria", "austria": "austria",
    "ungarn": "hungary", "hungary": "hungary",
    "senegal": "senegal", "kamerun": "cameroon", "cameroon": "cameroon",
    "ghana": "ghana", "nigeria": "nigeria",
    "kolumbien": "colombia", "colombia": "colombia",
    "ecuador": "ecuador", "chile": "chile",
    "costa rica": "costa rica", "panama": "panama", "honduras": "honduras",
    "jamaika": "jamaica", "jamaica": "jamaica",
    "el salvador": "el salvador", "guatemala": "guatemala",
    "jordanien": "jordan", "jordan": "jordan",
    "usbekistan": "uzbekistan", "uzbekistan": "uzbekistan",
    "china": "china", "indonesien": "indonesia", "indonesia": "indonesia",
    "neuseeland": "new zealand",
}

_WM_TEAM_NAMES = set(_NORM.values())


def _norm_name(name):
    n = re.sub(r"(?i)^(?:die|der|das|dem|den)\s+", "", name.strip().lower())
    if n in _NORM:
        return _NORM[n]
    n2 = (n.replace("ü", "u").replace("ö", "o").replace("ä", "a")
          .replace("ß", "ss").replace("é", "e").replace("ç", "c").replace("'", "'"))
    if n2 in _NORM:
        return _NORM[n2]
    return n2


def _is_wm_team_key(key):
    """True if both teams in the key are recognised WM national teams."""
    if not key:
        return False
    return all(t in _WM_TEAM_NAMES for t in key.split("|"))


def _clean_yt_for_teams(t):
    """Strip YouTube noise to leave just team names. NOT for Sportschau titles."""
    # Remove emojis and everything after
    t = re.sub(r"[\U0001F000-\U0001FFFF].*", "", t).strip()
    # Remove | suffix
    t = re.split(r"\s*\|", t)[0].strip()
    # Remove "Extended Highlights ..." suffix
    t = re.sub(r"\s+(?:Extended\s+)?Highlights?\b.*$", "", t, flags=re.I).strip()
    # Remove " FIFA ...", " World Cup ..." suffix (not standalone "2026" — too greedy)
    t = re.sub(r"\s+(?:FIFA\b|World Cup\b).*$", "", t, flags=re.I).strip()
    # Remove comma-separated suffixes
    t = re.sub(r",.*$", "", t).strip()
    return t


def _team_key(title):
    t = title.strip()
    # Sportschau game: "WM 2026 T1 gegen T2 - die Highlights"
    m = re.match(r"WM \d{4}\s+(.+?)\s+gegen\s+(.+?)(?:\s*-.*)?$", t, re.I)
    if m:
        return "|".join(sorted([_norm_name(m.group(1)), _norm_name(m.group(2))]))
    # Other Sportschau titles starting with "WM YYYY" → no game key
    if re.match(r"WM \d{4}", t, re.I):
        return None
    # YouTube: clean noise first, then split on separator
    t2 = _clean_yt_for_teams(t)
    parts = re.split(r"\s+(?:vs\.|vs|gegen|-)\s+", t2)
    if len(parts) == 2:
        return "|".join(sorted([_norm_name(parts[0]), _norm_name(parts[1])]))
    return None


def _display_title(title):
    """Return a clean display title."""
    t = title.strip()
    # Sportschau game: "WM 2026 T1 gegen T2 - die Highlights" → "T1 – T2"
    m = re.match(r"WM \d{4}\s+(.+?)\s+gegen\s+(.+?)(?:\s*-\s*die.*)?$", t, re.I)
    if m:
        strip_art = lambda s: re.sub(r"(?i)^(?:die|der|das|dem|den)\s+", "", s).strip()
        return f"{strip_art(m.group(1))} – {strip_art(m.group(2))}"
    # Other Sportschau titles (starts with "WM YYYY"): show as-is
    if re.match(r"WM \d{4}", t, re.I):
        return t
    # YouTube title: clean and format
    t2 = _clean_yt_for_teams(t)
    t2 = re.sub(r"\s+vs\.\s+", " – ", t2)
    t2 = re.sub(r"\s+-\s+", " – ", t2)
    return t2 or title

# ---------- duration ----------

def _parse_iso_dur(d):
    if not d:
        return None
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d)
    if not m:
        return None
    total = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return total or None


def _parse_mmss(text):
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        pass
    return None


def _fmt_dur(secs):
    if not secs:
        return ""
    m, s = divmod(int(secs), 60)
    return f"{m}:{s:02d}"

# ---------- datetime ----------

def _parse_iso(raw):
    if not raw:
        return ""
    raw = re.sub(r"\+0000$", "+00:00", raw.strip())
    raw = re.sub(r"Z$", "+00:00", raw)
    try:
        return datetime.fromisoformat(raw).astimezone(timezone.utc).isoformat()
    except Exception:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T00:00:00+00:00" if m else ""


def _fmt_date(iso):
    if not iso:
        return ""
    try:
        # Date-only strings (no T component): show without time
        if "T" not in iso:
            d = datetime.fromisoformat(iso + "T00:00:00")
            return d.strftime("%d.%m.")
        dt = datetime.fromisoformat(iso).astimezone(CEST)
        return dt.strftime("%d.%m. %H:%M")
    except Exception:
        return ""

def _get_yt_date(video_url):
    """Fetch publish date from a YouTube video page. Returns date-only 'YYYY-MM-DD' or ''."""
    try:
        html = _http(video_url)
        # publishDate in ytInitialData: {"simpleText":"17.06.2026"}
        m = re.search(r'"publishDate"\s*:\s*\{"simpleText"\s*:\s*"(\d{2}\.\d{2}\.\d{4})"', html)
        if m:
            day, mon, year = m.group(1).split(".")
            return f"{year}-{mon}-{day}"
        # Fallback: dateText
        m2 = re.search(r'"dateText"\s*:\s*\{"simpleText"\s*:\s*"(\d{2}\.\d{2}\.\d{4})"', html)
        if m2:
            day, mon, year = m2.group(1).split(".")
            return f"{year}-{mon}-{day}"
    except Exception:
        pass
    return ""

# ---------- Sportschau ----------

def _http(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


_EXCLUDE = ["paralympics"]


def _is_highlight(title, href):
    t, h = title.lower(), href.lower()
    return (
        not any(x in t or x in h for x in _EXCLUDE)
        and ("highlight" in t or "highlight" in h)
    )


def _extract_listing(html):
    hu = unescape(html)
    iso_by_url = {}
    for m in re.finditer(r'"broadcastedOnDateTime":"([^"]+)"', hu):
        after = hu[m.start(): m.start() + 600]
        lm = re.search(r'"link":"(https://www\.sportschau\.de[^"]+)"', after)
        if lm:
            iso_by_url[lm.group(1)] = _parse_iso(m.group(1))
    out = {}
    for href, inner in re.findall(
        r'<a\s[^>]*href="(/[^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE
    ):
        h2 = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", inner, re.DOTALL | re.IGNORECASE)
        if not h2:
            continue
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h2.group(1))).strip()
        if not title or not _is_highlight(title, href):
            continue
        key = re.sub(r",[\w-]+\.html$", "", href)
        full = "https://www.sportschau.de" + href
        if key not in out:
            out[key] = (title, full, iso_by_url.get(full, ""))
    return out


def _extract_video(page_url):
    video_url = iso_str = None
    dur = None
    try:
        html = _http(page_url)
        for blob in re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        ):
            try:
                d = json.loads(blob)
                for item in (d if isinstance(d, list) else [d]):
                    if item.get("@type") == "VideoObject":
                        video_url = video_url or item.get("contentUrl")
                        dur = dur or _parse_iso_dur(item.get("duration"))
                        iso_str = iso_str or _parse_iso(
                            item.get("datePublished") or item.get("dateModified")
                        )
                    elif not iso_str and item.get("@type") in ("NewsArticle", "Article", "WebPage"):
                        iso_str = _parse_iso(
                            item.get("datePublished") or item.get("dateModified")
                        )
            except Exception:
                pass
    except Exception as e:
        print(f"  Fehler {page_url}: {e}", file=sys.stderr)
    return video_url, iso_str, dur

# ---------- YouTube ----------

def _yt_filter(items_raw, label="", prefer_standard=False):
    """Filter highlight videos, deduplicate by team key.
    prefer_standard=True: when standard + livekommentar exist, keep standard.
    """
    # Collect per-key best candidate
    keyed = {}   # key → item (lower priority = standard preferred)
    unkeyed = []
    for item in items_raw:
        t = item.get("title") or ""
        tl = t.lower()
        if "highlight" not in tl:
            continue
        if "extended" in tl:
            continue
        is_lk = "livekommentar" in tl or "live commentary" in tl
        key = _team_key(t)
        tagged = {**item, "team_key": key}
        if key:
            if key not in keyed:
                keyed[key] = tagged
            elif prefer_standard and is_lk is False and (
                "livekommentar" in (keyed[key].get("title") or "").lower()
                or "live commentary" in (keyed[key].get("title") or "").lower()
            ):
                # Replace livekommentar with standard
                keyed[key] = tagged
        else:
            if not is_lk:  # Only add unkeyed items if they're standard
                unkeyed.append(tagged)
    out = list(keyed.values()) + unkeyed
    if label:
        print(f"  {label}: {len(out)} aus {len(items_raw)}", file=sys.stderr)
    return out


def _ytdlp_fetch(url, from_playlist=False):
    try:
        r = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--dump-json",
             "--playlist-end", str(YT_LIMIT), "--no-warnings", url],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0 and r.stderr:
            print(f"  yt-dlp rc={r.returncode}: {r.stderr[:150]}", file=sys.stderr)
    except Exception as e:
        print(f"  yt-dlp error: {e}", file=sys.stderr)
        return []
    raw = []
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        vid = d.get("id", "")
        if not vid:
            continue
        # Only accept videos from the MagentaSport channel
        cid = d.get("channel_id") or d.get("uploader_id") or ""
        if cid and cid != YT_CHANNEL_ID:
            continue
        dur = d.get("duration")
        raw.append({
            "title": d.get("title") or "",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "duration_sec": int(dur) if dur else None,
            "from_playlist": from_playlist,
        })
    return raw


def _find_video_renderers(obj):
    if isinstance(obj, dict):
        if "videoId" in obj and "title" in obj:
            yield obj
        else:
            for v in obj.values():
                yield from _find_video_renderers(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _find_video_renderers(item)


def _ythtml_fetch(url):
    try:
        html = _http(url)
        idx = html.find("var ytInitialData = ")
        if idx == -1:
            return []
        idx += len("var ytInitialData = ")
        data, _ = json.JSONDecoder().raw_decode(html, idx)
    except Exception as e:
        print(f"  ytInitialData error: {e}", file=sys.stderr)
        return []
    raw = []
    for vd in _find_video_renderers(data):
        vid = vd.get("videoId", "")
        if not vid:
            continue
        runs = vd.get("title", {}).get("runs", [])
        title = "".join(r.get("text", "") for r in runs)
        if not title:
            continue
        dur_text = (vd.get("lengthText") or vd.get("length") or {}).get("simpleText", "")
        raw.append({
            "title": title,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "duration_sec": _parse_mmss(dur_text),
        })
    return raw


def _merge_yt(existing, new_items):
    seen_keys = {i["team_key"] for i in existing if i.get("team_key")}
    seen_urls = {i["url"] for i in existing}
    for item in new_items:
        k = item.get("team_key")
        if item["url"] in seen_urls:
            continue
        if k and k in seen_keys:
            continue
        if k:
            seen_keys.add(k)
        seen_urls.add(item["url"])
        existing.append(item)
    return existing


def _fetch_yt():
    # Primary: WM 2026 Highlights playlist (geo-independent, curated)
    # prefer_standard=True: if both standard + livekommentar exist for a game, keep standard
    raw = _ytdlp_fetch(YT_WM_PLAYLIST, from_playlist=True)
    items = _yt_filter(raw, "playlist", prefer_standard=True)

    # Fallback: ytInitialData from playlist page
    if len(items) < 5:
        raw2 = _ythtml_fetch(YT_WM_PLAYLIST)
        for item in raw2:
            item["from_playlist"] = True
        items = _merge_yt(items, _yt_filter(raw2, "ytInitialData playlist", prefer_standard=True))

    # Second fallback: channel /videos
    if len(items) < 5:
        raw3 = _ytdlp_fetch(YT_CHANNEL + "/videos")
        items = _merge_yt(items, _yt_filter(raw3, "channel /videos"))

    print(f"  → {len(items)} YouTube-Highlights.", file=sys.stderr)
    return items

# ---------- HTML ----------

_CSS = """
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #0f0f0f;
      color: #e0e0e0;
      padding: 2rem 1rem;
      max-width: 720px;
      margin: 0 auto;
    }
    h1 { font-size: 1.35rem; font-weight: 600; margin-bottom: 0.3rem; color: #fff; }
    .ts { font-size: 0.74rem; color: #444; margin-bottom: 1.8rem; }
    table { width: 100%; border-collapse: collapse; }
    tr + tr { border-top: 1px solid #1a1a1a; }
    td { padding: 0.65rem 0.4rem; vertical-align: top; }
    td.n {
      color: #333; font-size: 0.78rem; width: 2rem;
      text-align: right; padding-right: 0.7rem; padding-top: 0.82rem;
    }
    .ti { font-size: 0.93rem; color: #ccc; margin-bottom: 0.28rem; line-height: 1.3; }
    .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; }
    .dt { color: #464646; font-size: 0.73rem; margin-right: 1px; }
    .btn {
      display: inline-block; padding: 2px 8px; border-radius: 3px;
      font-size: 0.73rem; font-weight: 500; text-decoration: none; white-space: nowrap;
    }
    .ba { background: #162840; color: #5b9bcc; }
    .ba:hover { background: #1d3654; color: #78b0d8; }
    .by { background: #380f0f; color: #d45050; }
    .by:hover { background: #4f1515; color: #e87070; }
    @media (max-width: 500px) {
      td.n { display: none; }
      body { padding: 1.2rem 0.65rem; }
      .ti { font-size: 0.9rem; }
    }
"""


def _generate_html(items, ts):
    rows = []
    for i, item in enumerate(items, 1):
        date_str = _fmt_date(item.get("iso", ""))
        ard_url = item.get("ard_url")
        ard_dur = _fmt_dur(item.get("ard_dur"))
        yt_url = item.get("yt_url")
        yt_dur = _fmt_dur(item.get("yt_dur"))

        badges = []
        if ard_url:
            lbl = f"ARD{(' · ' + ard_dur) if ard_dur else ''}"
            badges.append(
                f'<a class="btn ba" href="{ard_url}" target="_blank" rel="noopener">{lbl}</a>'
            )
        if yt_url:
            lbl = f"YT{(' · ' + yt_dur) if yt_dur else ''}"
            badges.append(
                f'<a class="btn by" href="{yt_url}" target="_blank" rel="noopener">{lbl}</a>'
            )

        date_html = f'<span class="dt">{date_str}</span>' if date_str else ""
        meta = date_html + "".join(badges)

        rows.append(
            f"<tr>"
            f"<td class='n'>{i}</td>"
            f"<td><div class='ti'>{item['title']}</div>"
            f"<div class='meta'>{meta}</div></td>"
            f"</tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WM 2026 Highlights</title>
  <style>{_CSS}  </style>
</head>
<body>
  <h1>WM 2026 Highlights</h1>
  <p class="ts">Aktualisiert: {ts}</p>
  <table>
{"".join(chr(10) + "    " + r for r in rows)}
  </table>
</body>
</html>
"""

# ---------- main ----------


def main():
    merged = {}
    for url in SPORTSCHAU_SOURCES:
        print(f"Lade {url} ...", file=sys.stderr)
        html = _http(url)
        items = _extract_listing(html)
        new = {k: v for k, v in items.items() if k not in merged}
        merged.update(new)
        print(f"  {len(items)} Highlights, {len(new)} neu → gesamt {len(merged)}", file=sys.stderr)

    print(f"\nHole Video-Details ({len(merged)}) ...", file=sys.stderr)
    sp_raw = []
    for i, (title, page_url, iso) in enumerate(merged.values(), 1):
        print(f"  [{i}/{len(merged)}] {title}", file=sys.stderr)
        video_url, page_iso, dur = _extract_video(page_url)
        if not iso and page_iso:
            iso = page_iso
        sp_raw.append((title, iso, video_url, dur, _team_key(title)))

    # Deduplicate Sportschau by team_key (prefer entry with video URL)
    sp_items = []
    sp_seen = set()
    for item in sorted(sp_raw, key=lambda x: (0 if x[2] else 1)):  # video URL first
        key = item[4]
        if key and key in sp_seen:
            continue
        if key:
            sp_seen.add(key)
        sp_items.append(item)

    print(f"\nHole YouTube-Highlights ...", file=sys.stderr)
    yt_list = _fetch_yt()
    yt_by_key = {yt["team_key"]: yt for yt in yt_list if yt.get("team_key")}

    combined = []
    used_keys = set()
    for title, iso, ard_url, ard_dur, key in sp_items:
        yt = yt_by_key.get(key) if key else None
        if key:
            used_keys.add(key)
        combined.append({
            "title": _display_title(title),
            "iso": iso,
            "ard_url": ard_url,
            "ard_dur": ard_dur,
            "yt_url": yt["url"] if yt else None,
            "yt_dur": yt["duration_sec"] if yt else None,
        })

    # YouTube-only: add if from the WM playlist (always valid) or recognised WM teams
    yt_only_entries = []
    for key, yt in yt_by_key.items():
        if key not in used_keys and (yt.get("from_playlist") or _is_wm_team_key(key)):
            yt_only_entries.append({
                "title": _display_title(yt["title"]),
                "iso": "",
                "ard_url": None,
                "ard_dur": None,
                "yt_url": yt["url"],
                "yt_dur": yt["duration_sec"],
            })

    # Fetch dates for YouTube-only entries
    if yt_only_entries:
        print(f"  Hole Datum für {len(yt_only_entries)} YT-only Einträge ...", file=sys.stderr)
        for entry in yt_only_entries:
            entry["iso"] = _get_yt_date(entry["yt_url"])
    combined.extend(yt_only_entries)

    # Drop entries with no links at all (audio-only, text summaries)
    combined = [c for c in combined if c.get("ard_url") or c.get("yt_url")]

    combined.sort(key=lambda x: x["iso"] or "0000", reverse=True)

    ts = datetime.now(CEST).strftime("%d.%m.%Y %H:%M")
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(_generate_html(combined, ts))
    print("index.html geschrieben.", file=sys.stderr)


if __name__ == "__main__":
    main()

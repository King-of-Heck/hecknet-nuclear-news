"""
Nuclear news ticker.

Polls a set of RSS feeds every ten minutes and prints any story matching the
keyword list. Everything from World Nuclear News prints regardless of keywords.

Stories already seen are tracked by GUID so nothing prints twice, and that
record persists to nuclear_news_seen.json next to this file, so a restart does
not lose it. Backlog is held back by age rather than by marking everything
currently in the feeds as seen: an unseen story older than MAX_BACKFILL_AGE is
recorded without being printed. Blanket seeding happens only on a true first
run, when no state file exists yet.

Feeds are fetched in a round-robin across hosts, with a minimum gap between two
requests to the same host and backoff on HTTP 429, because some publishers
rate-limit a burst of section feeds hard.

    python nuclear_news.py
"""

from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests
import win32print
import win32ui
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageWin


PRINTER_NAME = "XP-80C"

FONT_PATH    = "cour.ttf"
FONT_BOLD    = "courbd.ttf"
FONT_SIZE    = 28           # slightly smaller so summaries fit nicely
RENDER_SCALE = 4

PRINTER_DPI  = 203
PAPER_MM     = 80
PAPER_PX     = int(PAPER_MM / 25.4 * PRINTER_DPI)   # ≈ 638 px
MARGIN_PX    = 10
TEXT_PX      = PAPER_PX - 2 * MARGIN_PX

POLL_INTERVAL = 600         # seconds between feed checks (10 minutes)
MIN_SLEEP     = 60          # never start the next poll sooner than this, even
                            # if the last one overran POLL_INTERVAL

# Keywords to watch for (case-insensitive).
# Each entry is a plain string; we do whole-word / flexible matching below.
KEYWORDS = ["nuclear", "candu", "ap1000", "ap 1000", "monark",
            "opg", "ontario power generation", "bruce power",
            "sizewell", "hinkley point", "edf", "framatome", "cnsc", "aecl"]

RSS_FEEDS = [
    # The Globe reorganised its section taxonomy: technology, science, health,
    # environment, economy and arts no longer exist as top-level categories.
    # The old URLs for them still answer 200 with a valid but permanently
    # empty <channel> (~1 KB, zero <item>s), because the endpoint is a
    # catch-all, which is why they failed silently. Verified 2026-10-27.
    # Arc accepts nested paths, so the replacements below are the real homes
    # of that coverage. Environment has no successor section -- the Globe
    # spreads climate across others -- and energy-and-resources carries more
    # nuclear copy than a general environment feed would anyway.
    ("Globe & Mail: Canada",                 "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/"),
    ("Globe & Mail: Business",               "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/"),
    ("Globe & Mail: Politics",               "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/politics/"),
    ("Globe & Mail: World",                  "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/world/"),
    ("Globe & Mail: Opinion",                "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/opinion/"),
    ("Globe & Mail: Technology",             "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/technology/"),
    ("Globe & Mail: Economy",                "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/economy/"),
    ("Globe & Mail: Energy & Resources",     "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/industry-news/energy-and-resources/"),
    ("Globe & Mail: Science",                "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/science/"),
    ("Globe & Mail: Health",                 "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/life/wellness/"),
    ("Globe & Mail: Culture",                "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/culture/"),
    ("Globe & Mail: Real Estate",            "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/real-estate/"),
    ("Globe & Mail: Life",                   "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/life/"),


    ("World Nuclear News",          "https://world-nuclear-news.org/rss"),

    ("NYT: Home",                   "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml"),
    ("NYT: World",                  "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("NYT: US",                     "https://rss.nytimes.com/services/xml/rss/nyt/US.xml"),
    ("NYT: Politics",               "https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"),
    ("NYT: Business",               "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("NYT: Technology",             "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"),
    ("NYT: Science",                "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml"),
    ("NYT: Health",                 "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml"),
    ("NYT: Climate",                "https://rss.nytimes.com/services/xml/rss/nyt/Climate.xml"),

    ("BBC: Top Stories",            "https://feeds.bbci.co.uk/news/rss.xml"),
    ("BBC: World",                  "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC: UK",                     "https://feeds.bbci.co.uk/news/uk/rss.xml"),
    ("BBC: Business",               "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC: Technology",             "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("BBC: Science & Environment",  "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("BBC: Health",                 "https://feeds.bbci.co.uk/news/health/rss.xml"),
    ("BBC: Politics",               "https://feeds.bbci.co.uk/news/politics/rss.xml"),
    ("BBC: World: Asia",            "https://feeds.bbci.co.uk/news/world/asia/rss.xml"),
    ("BBC: World: Europe",          "https://feeds.bbci.co.uk/news/world/europe/rss.xml"),

    # Financial Times
    # Note: FT may require a subscription session for some feeds.
    ("FT: Home",                    "https://www.ft.com/rss/home"),
    ("FT: World",                   "https://www.ft.com/world?format=rss"),
    ("FT: UK",                      "https://www.ft.com/world/uk?format=rss"),
    ("FT: US",                      "https://www.ft.com/world/us?format=rss"),
    ("FT: Europe",                  "https://www.ft.com/world/europe?format=rss"),
    ("FT: Asia-Pacific",            "https://www.ft.com/world/asia-pacific?format=rss"),
    ("FT: Global Economy",          "https://www.ft.com/global-economy?format=rss"),
    ("FT: Energy",                  "https://www.ft.com/energy?format=rss"),
    ("FT: Companies",               "https://www.ft.com/companies?format=rss"),

    # thestar.com runs on TownNews/BLOX. The old AEM feed.RSSManagerServlet.*
    # URLs are gone — every one of them returns the same 312 KB "RSS Feeds"
    # HTML landing page (HTTP 200, text/html, zero items) and counts against a
    # tight per-IP rate limit, which is what produced the 429 storm. These are
    # the BLOX search feeds listed on thestar.com/site/static-pages/rss-feeds.html.
    # The "*" suffix is a BLOX wildcard: news* also covers news/canada,
    # news/gta and news/world, so a handful of feeds replaces the old eleven.
    # Three feeds, not more: measured, the Star starts returning 429 at about
    # the fourth request in a window. news* already covers news/canada,
    # news/gta and news/world, and at l=50 each these three carry the Star's
    # whole nuclear-relevant output. Top stories (bl=2827101) is a subset of
    # news*, and opinion* rarely matches the keyword list, so neither is worth
    # a slot. Other sections are listed at
    # thestar.com/site/static-pages/rss-feeds.html if the budget ever allows.
    ("Toronto Star: News",          "https://www.thestar.com/search/?f=rss&t=article&c=news*&l=50&s=start_time&sd=desc"),
    ("Toronto Star: Business",      "https://www.thestar.com/search/?f=rss&t=article&c=business*&l=50&s=start_time&sd=desc"),
    ("Toronto Star: Politics",      "https://www.thestar.com/search/?f=rss&t=article&c=politics*&l=50&s=start_time&sd=desc"),
]

HEADERS = {
    "User-Agent": "nuclear-news-receipt/1.0",
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
}

# One session for the whole run so connections are kept alive between polls.
SESSION = requests.Session()

# Politeness. Feeds are fetched in a host round-robin (see interleave_by_host),
# so these gaps almost never cost real time — by the time we come back to a
# host, the gap has already elapsed while other hosts were being fetched.
DEFAULT_HOST_GAP = 1.0      # seconds between two requests to the same host
HOST_MIN_GAP = {
    # thestar.com rate-limits per IP, and harder than first measured. At 30s
    # apart the third Star request of a poll (Politics) was refused with 429
    # about every other poll, and so was its retry a minute later; the first
    # request of the next poll, ten minutes on, always went through. So the
    # window is minutes, not seconds. 120s apart puts the three requests at
    # 0, 120 and 240s; worst case, with a refusal and one retry, a poll still
    # finishes inside the 600s interval. It sends no Retry-After header.
    "www.thestar.com": 120.0,
}
MAX_HOST_GAP    = 90.0      # ceiling for the adaptive backoff below
RETRIES_ON_429  = 1         # extra attempts after the first 429. One is
                            # enough: a feed that still fails is simply picked
                            # up on the next poll ten minutes later, which is
                            # cheaper than stalling this one.


# Pre-compile a single OR pattern; \b gives word boundaries where sensible.
# "ap 1000" has a space so we handle it literally; others get \b guards.
_KW_PATTERN = re.compile(
    r'\b(?:nuclear|candu|ap1000|monark|opg|edf|framatome|cnsc|aecl|sizewell)\b'
    r'|ap\s+1000|ontario\s+power\s+generation|bruce\s+power|hinkley\s+point',
    re.IGNORECASE
)

def contains_keyword(text: str) -> bool:
    return bool(_KW_PATTERN.search(text))

def ts() -> str:
    """Current timestamp string for console logging."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Seen-item persistence. Without it the seen set lived only in memory, so every
# restart started from nothing, and to keep that restart from printing the
# whole backlog the first pass marked everything currently in every feed as
# seen without printing it -- which meant a restart silently swallowed every
# story still listed, up to a fortnight of them. Persisting the set makes a
# restart cheap; the age cutoff below is what holds the backlog back.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE   = os.path.join(_SCRIPT_DIR, "nuclear_news_seen.json")
_SEEN_NAME  = os.path.basename(SEEN_FILE)

# An unseen story older than this is recorded but not printed. The feeds carry
# up to a fortnight of history, so without this guard the first poll after a
# restart would treat all of it as new.
MAX_BACKFILL_AGE = timedelta(hours=24)

# How long an ID is remembered. This MUST exceed the longest feed window, or a
# story could be forgotten while still listed and print a second time.
# Measured 2026-11-08, the longest of the 45 feeds is the Globe opinion feed at
# 14 days; 30 leaves comfortable margin.
SEEN_RETENTION = timedelta(days=30)

# Safety valve on file size, independent of the age rule above. 45 feeds at
# ~100 items each is roughly 4,500 live IDs, so this leaves about 4x headroom.
MAX_SEEN_ENTRIES = 20000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_date(raw):
    """
    Parse an RSS pubDate (RFC 822) or an Atom published/updated (ISO 8601)
    into an aware UTC datetime. Returns None when it cannot be read, in which
    case the caller treats the item as current rather than guessing.
    """
    if not raw:
        return None
    raw = raw.strip()
    dt = None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_seen():
    """
    Load the persisted {item id: ISO timestamp first seen} map.

    Returns (seen, first_run). first_run is True only when there is no state
    file at all -- the single case where the current contents of every feed is
    swallowed silently, so a fresh install prints no backlog. A file that
    exists but cannot be read is deliberately NOT a first run: say so loudly
    and fall back to the age cutoff, which prints a day rather than a
    fortnight or nothing at all.
    """
    if not os.path.exists(SEEN_FILE):
        return {}, True
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        seen = data["seen"]
        if not isinstance(seen, dict):
            raise ValueError("'seen' is not an object")
        return {str(k): str(v) for k, v in seen.items()}, False
    except Exception as e:
        hours = int(MAX_BACKFILL_AGE.total_seconds() // 3600)
        print(f"[{ts()}] [WARNING] {_SEEN_NAME} could not be read ({e}). "
              f"It will be rewritten; only the last {hours}h will print.")
        return {}, False


def prune_seen(seen):
    """
    Drop IDs older than SEEN_RETENTION, then cap the total, oldest first.

    An entry with an unreadable timestamp is re-stamped rather than dropped:
    dropping it would let that story print again, which is the one outcome
    this whole mechanism exists to prevent.
    """
    now_iso = _utc_now_iso()
    cutoff  = datetime.now(timezone.utc) - SEEN_RETENTION
    kept = {}

    for item_id, first_seen in seen.items():
        try:
            when = datetime.fromisoformat(first_seen)
        except (TypeError, ValueError):
            kept[item_id] = now_iso
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            kept[item_id] = first_seen

    if len(kept) > MAX_SEEN_ENTRIES:
        newest = sorted(kept.items(), key=lambda kv: kv[1], reverse=True)
        kept = dict(newest[:MAX_SEEN_ENTRIES])
    return kept


def save_seen(seen):
    """
    Write the map atomically, so a crash or power cut mid-write cannot leave a
    truncated file behind. A corrupt file costs a day of backfill, so the
    rename is worth it.
    """
    tmp = SEEN_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "seen": seen}, fh)
        os.replace(tmp, SEEN_FILE)
    except OSError as e:
        print(f"[{ts()}] [WARNING] Could not write {_SEEN_NAME}: {e}")
        try:
            os.unlink(tmp)
        except OSError:
            pass


_last_request: dict[str, float] = {}   # host -> time.monotonic() of last fetch
_current_gap:  dict[str, float] = {}   # host -> gap in force, grows after a 429


def base_gap(host: str) -> float:
    return HOST_MIN_GAP.get(host, DEFAULT_HOST_GAP)


def interleave_by_host(feeds: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Reorder feeds so consecutive entries come from different hosts.

    RSS_FEEDS is grouped by publication because that is how it is read and
    edited, but fetching it in that order means eleven requests to one host
    back to back. Round-robin spreads each host's requests across the whole
    poll, which is both politer and faster than sleeping between them.
    """
    buckets: OrderedDict[str, list[tuple[str, str]]] = OrderedDict()
    for name, url in feeds:
        buckets.setdefault(urlsplit(url).netloc, []).append((name, url))

    ordered: list[tuple[str, str]] = []
    while buckets:
        for host in list(buckets):
            ordered.append(buckets[host].pop(0))
            if not buckets[host]:
                del buckets[host]
    return ordered


def _wait_for_host(host: str) -> None:
    """Sleep until this host's minimum gap has elapsed."""
    gap = _current_gap.get(host, base_gap(host))
    last = _last_request.get(host)
    if last is None:
        return
    remaining = gap - (time.monotonic() - last)
    if remaining > 0:
        time.sleep(remaining)


def _get(url: str):
    """
    GET with per-host pacing and backoff on HTTP 429.

    On a 429 the host's gap is doubled (up to MAX_HOST_GAP) and the request is
    retried; on success the gap decays back towards its baseline, so one busy
    moment does not slow the feed down for the rest of the session.
    """
    host = urlsplit(url).netloc

    for attempt in range(RETRIES_ON_429 + 1):
        _wait_for_host(host)
        r = SESSION.get(url, headers=HEADERS, timeout=15)
        _last_request[host] = time.monotonic()

        if r.status_code != 429:
            gap = _current_gap.get(host)
            if gap is not None:
                decayed = max(base_gap(host), gap / 2)
                if decayed <= base_gap(host):
                    _current_gap.pop(host, None)
                else:
                    _current_gap[host] = decayed
            r.raise_for_status()
            return r

        # The ceiling is never below the host's own baseline: with the Star
        # at 120s and MAX_HOST_GAP at 90s, a plain min() would turn a 429
        # into a *shorter* gap, the opposite of backing off.
        grown = min(max(base_gap(host), _current_gap.get(host, base_gap(host))) * 2,
                    max(MAX_HOST_GAP, base_gap(host)))
        _current_gap[host] = grown

        if attempt == RETRIES_ON_429:
            r.raise_for_status()        # out of retries: report it as before

        retry_after = r.headers.get("Retry-After")
        try:
            pause = float(retry_after) if retry_after else grown
        except ValueError:
            pause = grown
        print(f"[{ts()}] [{host}] 429; backing off {pause:.0f}s "
              f"(gap now {grown:.0f}s), retrying…")
        time.sleep(pause)


_HTML_TAG = re.compile(r"<[^>]+>")

def strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text).strip()

def _parse_entries_bs4(content: bytes) -> list:
    """Fallback parser using BeautifulSoup for malformed XML feeds."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, "xml")
    entries = soup.find_all("item") or soup.find_all("entry")
    return entries

def _text(tag, *names):
    """Try multiple tag names and return the first non-empty text found."""
    for name in names:
        el = tag.find(name)
        if el and el.get_text(strip=True):
            return el.get_text(strip=True)
    return ""

def fetch_items(source_name: str, url: str) -> list[dict] | None:
    """
    Returns a list of dicts with keys: id, title, summary, source,
    or None if the feed could not be fetched/parsed (distinct from an empty feed).
    Falls back to BeautifulSoup XML parser if stdlib ET chokes on malformed XML.
    """
    try:
        r = _get(url)
    except Exception as e:
        print(f"[{ts()}] [{source_name}] Fetch error: {e}")
        return None

    use_bs4 = False
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        use_bs4 = True

    items = []

    if use_bs4:
        try:
            raw_entries = _parse_entries_bs4(r.content)
        except Exception as e:
            print(f"[{ts()}] [{source_name}] BS4 parse error: {e}")
            return None

        for entry in raw_entries:
            title   = strip_html(_text(entry, "title"))
            summary = strip_html(_text(entry, "description", "summary", "content"))
            uid     = _text(entry, "guid", "id", "link") or title
            if title:
                items.append({
                    "id":        uid.strip(),
                    "title":     title,
                    "summary":   summary,
                    "source":    source_name,
                    "published": parse_date(
                        _text(entry, "pubDate", "published", "updated")),
                })
        return items

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)

    for entry in entries:
        title = strip_html(entry.findtext("title") or
                           entry.findtext("atom:title", namespaces=ns) or "")

        summary = (entry.findtext("description") or
                   entry.findtext("summary") or
                   entry.findtext("atom:summary", namespaces=ns) or
                   entry.findtext("atom:content", namespaces=ns) or "")
        summary = strip_html(summary)

        uid = (entry.findtext("guid") or
               entry.findtext("id") or
               entry.findtext("atom:id", namespaces=ns) or
               entry.findtext("link") or
               title)

        published = parse_date(
            entry.findtext("pubDate") or
            entry.findtext("published") or
            entry.findtext("atom:published", namespaces=ns) or
            entry.findtext("atom:updated", namespaces=ns) or
            entry.findtext("updated"))

        items.append({
            "id":        uid.strip(),
            "title":     title,
            "summary":   summary,
            "source":    source_name,
            "published": published,
        })

    return items


_reported_empty: set[str] = set()


def check_not_empty(source: str, url: str, items: list) -> None:
    """
    Report once when a feed answers 200 but carries no items.

    This is how the Toronto Star feeds failed: the server stopped serving RSS
    and started serving an HTML page, which parses cleanly and yields nothing.
    A fetch error is loud; an empty feed is silent, so say something.
    """
    if items:
        _reported_empty.discard(url)
    elif url not in _reported_empty:
        _reported_empty.add(url)
        print(f"[{ts()}]   [{source}] fetched OK but contains no items — "
              f"the feed URL may be dead.")


def load_font(bold=False):
    path = FONT_BOLD if bold else FONT_PATH
    try:
        return ImageFont.truetype(path, FONT_SIZE * RENDER_SCALE)
    except OSError:
        return ImageFont.load_default()

# EMOJI GLYPH HELPERS  (same technique as weather_receipt)
# Courier lacks  so we render it separately with Segoe UI Emoji

RADS_FONT_SIZE = 26   # pt — size of ☢ radioactivity glyphs
RADS_Y_OFFSET  = 36   # px at 4x — shifts rads symbol DOWN relative to text baseline

_EMOJI_FONT_CANDIDATES = [
    "seguiemj.ttf",
    "C:/Windows/Fonts/seguiemj.ttf",
    "seguisym.ttf",
]

def _load_emoji_font(size_pt: int):
    for path in _EMOJI_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size_pt * RENDER_SCALE)
        except OSError:
            continue
    return load_font(bold=True)

def _draw_flanked_header(draw, text: str, glyph: str,
                         font_text, font_glyph,
                         paper_w: int, y: int, y_offset: int):
    """Render  <glyph>  <text>  <glyph>  centred on the line."""
    gap     = int(font_text.size * 0.4)
    glyph_w = int(font_glyph.getlength(glyph))
    text_w  = int(font_text.getlength(text))
    total_w = glyph_w + gap + text_w + gap + glyph_w
    x = (paper_w - total_w) // 2
    draw.text((x, y + y_offset), glyph, font=font_glyph, fill="black")
    x += glyph_w + gap
    draw.text((x, y), text, font=font_text, fill="black")
    x += text_w + gap
    draw.text((x, y + y_offset), glyph, font=font_glyph, fill="black")

def wrap_text(text: str, font, max_width: int) -> list[str]:
    """Word-wrap text to fit max_width pixels."""
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if font.getlength(candidate) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]

def build_alert_image(source: str, title: str, summary: str, timestamp: str) -> Image.Image:
    """
    Render a nuclear-news alert receipt at 4x then downsample — same
    technique as weather_receipt.py for crisp thermal output.
    """
    S        = RENDER_SCALE
    paper_w  = PAPER_PX * S
    margin   = MARGIN_PX * S
    text_w   = TEXT_PX * S
    line_h   = int(FONT_SIZE * S * 1.35)

    font_n     = load_font(bold=False)
    font_b     = load_font(bold=True)
    font_rads  = _load_emoji_font(RADS_FONT_SIZE)
    DIVIDER    = "─" * 32

    ops = []

    def add(text, bold=False, align="left"):
        ops.append((text, font_b if bold else font_n, align))

    def div():
        add(DIVIDER)

    add("HECKNET NEWS NETWORK", bold=True, align="center")
    rads_op_idx = len(ops)
    add("", align="center")          # → ☢ NUCLEAR DISPATCH ☢
    add(timestamp,  align="center")
    div()

    add(f"SOURCE: {source.upper()}", bold=True)
    div()

    add("HEADLINE", bold=True)
    for line in wrap_text(title, font_b, text_w):
        add(line, bold=True)

    if summary:
        add("")         # spacer
        for line in wrap_text(summary, font_n, text_w):
            add(line)

    div()

    top_pad = RADS_Y_OFFSET
    total_h = len(ops) * line_h + line_h * 2 + top_pad
    hi_res  = Image.new("RGB", (paper_w, total_h), "white")
    draw    = ImageDraw.Draw(hi_res)
    y       = margin // 2 + top_pad

    for i, (text, font, align) in enumerate(ops):
        if align == "center":
            tw = font.getlength(text)
            x  = (paper_w - tw) / 2
        else:
            x = margin
        draw.text((x, y), text, font=font, fill="black")

        if i == rads_op_idx:
            _draw_flanked_header(draw, "NUCLEAR DISPATCH", "\u2622",
                                 font_b, font_rads, paper_w, y, RADS_Y_OFFSET)

        y += line_h

    out_w  = PAPER_PX
    out_h  = int(total_h / S)
    output = hi_res.resize((out_w, out_h), Image.LANCZOS)
    output = ImageEnhance.Contrast(output).enhance(2.5)
    output = output.convert("L").convert("RGB")

    final_h = int(y / S)
    return output.crop((0, 0, out_w, final_h))


def send_image_to_printer(pil_img: Image.Image):
    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(PRINTER_NAME)
    printer_w = hdc.GetDeviceCaps(110)  # HORZRES

    img_w, img_h = pil_img.size
    if img_w != printer_w:
        new_h   = int(img_h * printer_w / img_w)
        pil_img = pil_img.resize((printer_w, new_h), Image.LANCZOS)
        img_w, img_h = pil_img.size

    hdc.StartDoc("Nuclear News Alert")
    hdc.StartPage()
    dib = ImageWin.Dib(pil_img)
    dib.draw(hdc.GetHandleOutput(), (0, 0, img_w, img_h))
    hdc.EndPage()
    hdc.EndDoc()
    hdc.DeleteDC()

def print_alert(source: str, title: str, summary: str):
    timestamp = datetime.now().strftime("%a %b %d %Y  %I:%M %p")
    img = build_alert_image(source, title, summary, timestamp)
    send_image_to_printer(img)


def main():
    print(f"[{ts()}] Nuclear News Receipt Printer starting\u2026")
    print(f"[{ts()}] Keywords : {', '.join(KEYWORDS)}")
    print(f"[{ts()}] Interval : {POLL_INTERVAL}s ({POLL_INTERVAL // 60} min)")
    print(f"[{ts()}] Printer  : {PRINTER_NAME}")
    print(f"[{ts()}] State    : {SEEN_FILE}")
    print(f"[{ts()}] Press Ctrl-C to stop.\n")

    backfill_hours = int(MAX_BACKFILL_AGE.total_seconds() // 3600)

    seen, first_run = load_seen()
    before = len(seen)
    seen = prune_seen(seen)
    if before != len(seen):
        print(f"[{ts()}] Pruned {before - len(seen)} expired ID(s) from "
              f"{_SEEN_NAME}.")

    # Fetch order is round-robined across hosts so the per-host gap overlaps
    # with other hosts' requests instead of stalling the poll.
    poll_order = interleave_by_host(RSS_FEEDS)

    if first_run:
        # No state file at all. Swallow whatever the feeds hold right now so a
        # fresh install prints no backlog. This happens exactly once: from the
        # next start onwards the persisted set is what decides, and the age
        # cutoff below is what holds the backlog back.
        print(f"[{ts()}] No {_SEEN_NAME} yet, so this is a first run. Seeding "
              f"from current feeds (nothing will print)\u2026")
        now_iso = _utc_now_iso()
        seeded_urls = set()
        for source, url in poll_order:
            items = fetch_items(source, url)
            if items is None:
                continue
            check_not_empty(source, url, items)
            for item in items:
                seen[item["id"]] = now_iso
            seeded_urls.add(url)
        save_seen(seen)
        print(f"[{ts()}] Seeded {len(seen)} existing items. Watching for new "
              f"ones\u2026")
        unseeded = len(RSS_FEEDS) - len(seeded_urls)
        if unseeded:
            print(f"[{ts()}] {unseeded} feed(s) unreachable during seeding; "
                  f"when they return, their stories from the last "
                  f"{backfill_hours}h will print.")
    else:
        print(f"[{ts()}] Loaded {len(seen)} seen item(s) from {_SEEN_NAME}. "
              f"Unprinted stories from the last {backfill_hours}h will print; "
              f"anything older is recorded without printing.")
    print()

    while True:
        start   = time.monotonic()
        cutoff  = datetime.now(timezone.utc) - MAX_BACKFILL_AGE
        now_iso = _utc_now_iso()
        changed = False
        print(f"[{ts()}] Polling {len(RSS_FEEDS)} feeds\u2026")

        for source, url in poll_order:
            items = fetch_items(source, url)
            if items is None:
                continue
            check_not_empty(source, url, items)

            for item in items:
                if item["id"] in seen:
                    continue                        # already processed
                seen[item["id"]] = now_iso
                changed = True

                # Too old to be worth a receipt. This is the guard that makes
                # a restart cheap: the feeds still list up to a fortnight of
                # stories, and every one of them is unseen the first time a
                # new state file is consulted. An item we could not date is
                # treated as current rather than discarded.
                published = item.get("published")
                if published is not None and published < cutoff:
                    print(f"[{ts()}]   [old] [{source}] {item['title'][:60]}")
                    continue

                # World Nuclear News prints everything; all others need a keyword match
                is_wnn = "World Nuclear News" in item["source"]
                haystack = f"{item['title']} {item['summary']}"
                if is_wnn or contains_keyword(haystack):
                    try:
                        print(f"[{ts()}]   \u2192 MATCH [{source}] {item['title'][:70]}")
                        print_alert(item["source"], item["title"], item["summary"])
                    except Exception as e:
                        print(f"[{ts()}]   [PRINT ERROR] {e}")
                        # Leave it unseen so the next poll tries again, rather
                        # than losing the story to a paper jam or a printer
                        # that was switched off.
                        seen.pop(item["id"], None)
                else:
                    # Log non-matching new items quietly
                    print(f"[{ts()}]   [skip] [{source}] {item['title'][:60]}")

        if changed:
            seen = prune_seen(seen)
            save_seen(seen)

        elapsed = time.monotonic() - start
        sleep_for = max(MIN_SLEEP, POLL_INTERVAL - elapsed)
        if elapsed > POLL_INTERVAL:
            print(f"[{ts()}] Poll took {elapsed:.0f}s, longer than the "
                  f"{POLL_INTERVAL}s interval - a host is probably rate-limiting "
                  f"us. Sleeping {sleep_for:.0f}s rather than polling flat out.")
        print(f"[{ts()}] Poll complete in {elapsed:.1f}s. "
              f"Next check in {sleep_for:.0f}s\u2026\n")
        time.sleep(sleep_for)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n[{ts()}] Stopped.")

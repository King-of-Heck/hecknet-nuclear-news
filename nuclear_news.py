"""
"""

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime

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

# Keywords to watch for (case-insensitive).
# Each entry is a plain string; we do whole-word / flexible matching below.
KEYWORDS = ["nuclear", "candu", "ap1000", "ap 1000", "monark",
            "opg", "ontario power generation", "bruce power",
            "sizewell", "hinkley point", "edf", "framatome", "cnsc", "aecl"]

RSS_FEEDS = [
    ("Globe & Mail: Canada",        "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/canada/"),
    ("Globe & Mail: Business",      "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/business/"),
    ("Globe & Mail: Politics",      "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/politics/"),
    ("Globe & Mail: World",         "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/world/"),
    ("Globe & Mail: Opinion",       "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/opinion/"),
    ("Globe & Mail: Technology",    "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/technology/"),
    ("Globe & Mail: Science",       "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/science/"),
    ("Globe & Mail: Health",        "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/health/"),
    ("Globe & Mail: Environment",   "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/environment/"),
    ("Globe & Mail: Economy",       "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/economy/"),
    ("Globe & Mail: Real Estate",   "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/real-estate/"),
    ("Globe & Mail: Arts",          "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/arts/"),
    ("Globe & Mail: Life",          "https://www.theglobeandmail.com/arc/outboundfeeds/rss/category/life/"),

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

    ("Toronto Star: Top Stories",   "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.topstories.rss"),
    ("Toronto Star: News",          "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.news.rss"),
    ("Toronto Star: Business",      "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.business.rss"),
    ("Toronto Star: Politics",      "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.news.canada.politics.rss"),
    ("Toronto Star: World",         "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.news.world.rss"),
    ("Toronto Star: Opinion",       "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.opinion.rss"),
    ("Toronto Star: Science",       "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.news.sciencetech.rss"),
    ("Toronto Star: Environment",   "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.news.environment.rss"),
    ("Toronto Star: Life",          "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.life.rss"),
    ("Toronto Star: Entertainment", "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.entertainment.rss"),
    ("Toronto Star: Sports",        "https://www.thestar.com/content/thestar/feed.RSSManagerServlet.articles.sports.rss"),
]

HEADERS = {"User-Agent": "nuclear-news-receipt/1.0"}


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

def fetch_items(source_name: str, url: str) -> list[dict]:
    """
    Returns a list of dicts with keys: id, title, summary, source.
    Falls back to BeautifulSoup XML parser if stdlib ET chokes on malformed XML.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[{ts()}] [{source_name}] Fetch error: {e}")
        return []

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
            return []

        for entry in raw_entries:
            title   = strip_html(_text(entry, "title"))
            summary = strip_html(_text(entry, "description", "summary", "content"))
            uid     = _text(entry, "guid", "id", "link") or title
            if title:
                items.append({
                    "id":      uid.strip(),
                    "title":   title,
                    "summary": summary,
                    "source":  source_name,
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

        items.append({
            "id":      uid.strip(),
            "title":   title,
            "summary": summary,
            "source":  source_name,
        })

    return items


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
    print(f"[{ts()}] Nuclear News Receipt Printer starting…")
    print(f"[{ts()}] Keywords : {', '.join(KEYWORDS)}")
    print(f"[{ts()}] Interval : {POLL_INTERVAL}s ({POLL_INTERVAL // 60} min)")
    print(f"[{ts()}] Printer  : {PRINTER_NAME}")
    print(f"[{ts()}] Press Ctrl-C to stop.\n")

    # IDs of items we have already printed (grows forever during the session;
    # restart the script to reset, or persist to a file if preferred).
    seen_ids: set[str] = set()

    print(f"[{ts()}] Seeding seen items from current feeds (no printing on first pass)…")
    for source, url in RSS_FEEDS:
        for item in fetch_items(source, url):
            seen_ids.add(item["id"])
    print(f"[{ts()}] Seeded {len(seen_ids)} existing items. Watching for new ones…\n")

    while True:
        start = time.monotonic()
        print(f"[{ts()}] Polling {len(RSS_FEEDS)} feeds…")

        for source, url in RSS_FEEDS:
            items = fetch_items(source, url)
            for item in items:
                if item["id"] in seen_ids:
                    continue                        # already processed
                seen_ids.add(item["id"])

                is_wnn = "World Nuclear News" in item["source"]
                haystack = f"{item['title']} {item['summary']}"
                if is_wnn or contains_keyword(haystack):
                    try:
                        print(f"[{ts()}]    MATCH [{source}] {item['title'][:70]}")
                        print_alert(item["source"], item["title"], item["summary"])
                    except Exception as e:
                        print(f"[{ts()}]   [PRINT ERROR] {e}")
                else:
                    print(f"[{ts()}]   [skip] [{source}] {item['title'][:60]}")

        elapsed = time.monotonic() - start
        sleep_for = max(0, POLL_INTERVAL - elapsed)
        print(f"[{ts()}] Poll complete in {elapsed:.1f}s. Next check in {sleep_for:.0f}s…\n")
        time.sleep(sleep_for)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n[{ts()}] Stopped.")

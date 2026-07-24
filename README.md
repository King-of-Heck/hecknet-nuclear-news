# Nuclear News

Polls nuclear-industry RSS feeds and prints matching headlines to an XP-80C thermal printer.

Polls a set of RSS feeds every ten minutes and prints matching stories as they
appear. Sources include World Nuclear News, the Globe and Mail, the BBC, the
Financial Times and the Toronto Star.

Two matching rules apply:

- anything from World Nuclear News prints unconditionally
- everything else prints only if the title or description matches `KEYWORDS`

Already-printed stories are tracked by GUID or link, so nothing repeats.

Edit `FEEDS` and `KEYWORDS` at the top of the file to change coverage. The
poll interval is `POLL_SECONDS`; ten minutes is deliberate, since a shorter
interval got the feeds rate-limited.

## Requirements

- Windows. Printing goes through the Win32 GDI API.
- Python 3.10 or later.
- An 80mm thermal printer installed as a Windows printer. Built against an
  XP-80C at 203 DPI; other 80mm printers should work if the DPI matches.

```bash
pip install -r requirements.txt
```

Set `PRINTER_NAME` in `nuclear_news.py` to the printer's name as it appears in
Settings > Printers & scanners.

Receipts are rendered as images at 4x and downsampled before printing, which
is what keeps the text dark and legible on a thermal head. Courier is used
throughout; glyphs Courier lacks are composited from Segoe UI Emoji.

## Running

```bash
python nuclear_news.py
```

## Versioning

Tagged releases, with the change notes in [CHANGELOG.md](CHANGELOG.md).

## Licence

MIT. See [LICENSE](LICENSE).

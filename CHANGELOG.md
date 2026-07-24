# Changelog

Version numbers were reassigned for release (the old scheme bumped the
minor version for bugfixes); the original number is in parentheses. The
notes below are from each script's own version history.

## 1.5.1  (originally 1.7)

Fixed UnicodeEncodeError when piped through HeckNet Manager (Windows cp1252 can't
encode emoji). Added sys.stdout.reconfigure(UTF-8) and -u unbuffered flag support
so poll output streams in real time.

## 1.5.0  (originally 1.6)

Header changed to "NUCLEAR DISPATCH". Added ☢ radiation symbols flanking the
NUCLEAR DISPATCH line using Segoe UI Emoji (same technique as weather receipt).
Fixed black bar at bottom by tightening final crop.

## 1.4.0  (originally 1.5)

Poll interval increased from 60s to 10 minutes to avoid rate limiting. Timestamps
added to all console output for easier log monitoring.

## 1.3.0  (originally 1.4)

All World Nuclear News articles print unconditionally (no keyword filter). Added
keywords: Sizewell, Hinckley Point, EDF, Framatome, CNSC, AECL. Header updated to
"HECKNET NEWS NETWORK / NUCLEAR NEWSFLASH".

## 1.2.0  (originally 1.3)

Added more keywords (OPG, Ontario Power Generation, Bruce Power). Changed header
to HeckNet.

## 1.1.0  (originally 1.2)

Added all RSS feeds for Globe, WNN, BBC, FT and added the whole Toronto Star.

## 1.0.1  (originally 1.1)

Removes double cutting function

## 1.0.0  (originally 1.0)

First Version


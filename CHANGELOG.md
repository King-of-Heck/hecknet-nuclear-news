# Changelog

Version numbers were reassigned for release (the old scheme bumped the
minor version for bugfixes); the original number is in parentheses. The
notes below are from each script's own version history.

## 1.6.0

Fixed the Toronto Star 429 storm. The old `feed.RSSManagerServlet` URLs are
dead: thestar.com moved to the TownNews/BLOX platform and now answers all of
them with the same 312 KB "RSS Feeds" HTML landing page, so the eleven Star
feeds contributed zero articles while burning through the host's request budget
and tripping its rate limiter. Replaced them with five working BLOX search
feeds.

Repointed the six Globe and Mail category feeds (technology, science, health,
economy, arts and environment) that had been answering 200 with a permanently
empty channel ever since the Globe reorganised its sections. Arc accepts
nested paths, so these now point at `business/technology`, `canada/science`,
`life/wellness`, `business/economy` and `culture`. Environment has no
successor section, so its slot went to
`business/industry-news/energy-and-resources`, which carries more nuclear copy
than a general environment feed would.

Added polite fetching: one `requests.Session` for keep-alive, a minimum gap
between requests to the same host, adaptive backoff plus retry on HTTP 429, and
a poll order that round-robins across hosts so the per-host gap costs almost no
wall-clock time. A poll that overruns the interval now still waits before the
next one instead of polling flat out.

A feed that returns HTTP 200 but no items is now reported once, so the next
feed to die quietly does not go unnoticed.

## 1.5.2  (originally 1.8)

Feeds unreachable at startup (e.g. network outage) are now seeded silently on
their first successful fetch instead of printing their whole backlog.

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


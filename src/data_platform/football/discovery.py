"""Deterministic, whitelist-driven link discovery (D3, D6).

`requests` + regex only — no BeautifulSoup (D3). Given the HTML of each whitelisted
league landing page (fetched by the injected `fetch_html` callable, which in
production is the throttled HTTP client so pacing applies to page GETs too), emit a
deterministic, de-duplicated, family-tagged list of CSV URLs:

* **main** — ``mmz4281/<season>/<div>.csv`` links on a `<country>m.php` page; season
  and division are parsed from the URL path.
* **extra** — exactly ``new/<CODE>.csv`` for the page's whitelisted league code.

Off-list leagues are never fetched (only registry pages are), and within a page
non-matching links (aggregate ``Latest_Results.csv`` files, ``*.php`` ads/noise) are
filtered out. Relative and absolute links to the same file collapse to one entry.
Output order is a stable sort, so repeated runs over unchanged HTML are identical.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

from ..config import settings
from .registry import EXTRA_LEAGUES, MAIN_LEAGUES, ExtraLeague, Family, MainLeague

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
# Division codes are 1-3 upper-case letters + an optional digit (E0, EC, SC0, SP1, B1...).
# This deliberately excludes aggregate noise like `Latest_Results.csv`.
_MAIN_CSV_RE = re.compile(r"(?:^|/)mmz4281/(\d{4})/([A-Z]{1,3}\d?)\.csv$")
_EXTRA_CSV_RE = re.compile(r"(?:^|/)new/([A-Z]{2,4})\.csv$")


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    """One whitelisted source CSV, tagged with everything downstream needs."""

    family: Family
    league: str  # registry league name (e.g. "england", "argentina")
    url: str  # absolute CSV URL
    source_path: str  # path relative to the site root (e.g. "mmz4281/2324/E0.csv")
    season: str | None = None  # main: from URL ("2324"); extra: None (season in-file)
    division: str | None = None  # main: "E0"; extra: None
    code: str | None = None  # extra: "ARG"; main: None


def _hrefs(html: str) -> list[str]:
    return _HREF_RE.findall(html)


def _path_of(url: str) -> str:
    """Path portion of an absolute URL, leading slash stripped (no query/fragment)."""
    return urlsplit(url).path.lstrip("/")


def _discover_main(html: str, league: MainLeague, base_url: str) -> list[DiscoveredFile]:
    found: dict[str, DiscoveredFile] = {}
    for href in _hrefs(html):
        url = urljoin(base_url, href)
        m = _MAIN_CSV_RE.search(_path_of(url))
        if not m:
            continue
        season, division = m.group(1), m.group(2)
        found[url] = DiscoveredFile(
            family=Family.MAIN,
            league=league.name,
            url=url,
            source_path=f"mmz4281/{season}/{division}.csv",
            season=season,
            division=division,
        )
    return list(found.values())


def _discover_extra(html: str, league: ExtraLeague, base_url: str) -> list[DiscoveredFile]:
    found: dict[str, DiscoveredFile] = {}
    for href in _hrefs(html):
        url = urljoin(base_url, href)
        m = _EXTRA_CSV_RE.search(_path_of(url))
        if not m or m.group(1) != league.code:  # whitelist: only this league's code
            continue
        found[url] = DiscoveredFile(
            family=Family.EXTRA,
            league=league.name,
            url=url,
            source_path=f"new/{league.code}.csv",
            code=league.code,
        )
    return list(found.values())


def discover_files(
    fetch_html: Callable[[str], str],
    *,
    base_url: str | None = None,
    main_leagues: Iterable[MainLeague] = MAIN_LEAGUES,
    extra_leagues: Iterable[ExtraLeague] = EXTRA_LEAGUES,
) -> list[DiscoveredFile]:
    """Discover every whitelisted CSV across both families, deterministically.

    `fetch_html(url) -> html` is injected (the throttled client in production, a
    fixture map in tests). The result is de-duplicated by absolute URL and stably
    sorted, so repeated runs over unchanged source content are byte-for-byte equal.
    """
    base = base_url or settings.football_base_url
    files: dict[str, DiscoveredFile] = {}

    for league in main_leagues:
        html = fetch_html(urljoin(base, league.landing_page))
        for f in _discover_main(html, league, base):
            files[f.url] = f

    for extra in extra_leagues:
        html = fetch_html(urljoin(base, extra.landing_page))
        for f in _discover_extra(html, extra, base):
            files[f.url] = f

    return sorted(files.values(), key=lambda f: (f.family.value, f.league, f.url))


__all__ = ["DiscoveredFile", "discover_files"]

"""S3 — deterministic, whitelist-driven, family-tagged link discovery.

Discovery is pure given the page HTML: a `fetch_html` callable is injected so the
throttled client (S4) can carry pacing in production while tests use fixtures.
"""

from data_platform.football.discovery import DiscoveredFile, discover_files
from data_platform.football.registry import ExtraLeague, Family, MainLeague

BASE = "https://www.football-data.co.uk/"

ENGLAND = MainLeague("england", "englandm.php")
SCOTLAND = MainLeague("scotland", "scotlandm.php")
ARGENTINA = ExtraLeague("argentina", "argentina.php", "ARG")

# England main page: a real CSV linked BOTH relative and absolute (E6 dedup trap),
# a second real CSV, plus noise links that must be excluded (E5).
ENGLAND_HTML = """
<html><body>
  <a href="mmz4281/2324/E0.csv">E0 23/24 (relative)</a>
  <a href="https://www.football-data.co.uk/mmz4281/2324/E0.csv">E0 23/24 (absolute)</a>
  <a href="mmz4281/2223/E1.csv">E1 22/23</a>
  <a href="mmz4281/2526/Latest_Results.csv">aggregate noise file</a>
  <a href="blog/profitable_betting_system.php">profitable_betting_system.php</a>
  <a href="downloadm.php">downloadm.php</a>
</body></html>
"""

# Argentina extra page: the real new/ARG.csv plus an aggregate noise file.
ARGENTINA_HTML = """
<html><body>
  <a HREF="new/ARG.csv">Argentina</a>
  <a href="new/Latest_Results.csv">aggregate noise file</a>
  <a href="bet365_acca_boost.php">ad</a>
</body></html>
"""


def _fake_fetch(html_by_page: dict[str, str]):
    def fetch(url: str) -> str:
        for page, html in html_by_page.items():
            if url.endswith(page):
                return html
        raise AssertionError(f"unexpected fetch of off-list page: {url}")

    return fetch


def test_discovery_is_reproducible() -> None:
    fetch = _fake_fetch({"englandm.php": ENGLAND_HTML})
    first = discover_files(fetch, base_url=BASE, main_leagues=[ENGLAND], extra_leagues=[])
    second = discover_files(fetch, base_url=BASE, main_leagues=[ENGLAND], extra_leagues=[])
    assert first == second, "identical content AND order across runs"
    assert all(isinstance(f, DiscoveredFile) for f in first)


def test_relative_and_absolute_do_not_duplicate() -> None:
    fetch = _fake_fetch({"englandm.php": ENGLAND_HTML})
    files = discover_files(fetch, base_url=BASE, main_leagues=[ENGLAND], extra_leagues=[])
    e0 = [f for f in files if f.division == "E0"]
    assert len(e0) == 1, "rel + abs link to the same CSV must collapse to one entry"


def test_whitelist_excludes_noise_and_offlist() -> None:
    fetch = _fake_fetch({"englandm.php": ENGLAND_HTML})
    # Only england is whitelisted; scotland is never fetched (off-list).
    files = discover_files(fetch, base_url=BASE, main_leagues=[ENGLAND], extra_leagues=[])
    urls = {f.url for f in files}
    assert not any("Latest_Results" in u for u in urls), "aggregate noise excluded"
    assert not any(".php" in u for u in urls), "non-csv noise links excluded"
    assert all(f.league == "england" for f in files), "no off-list leagues emitted"
    # Exactly the two real fixtures (E0 deduped, E1).
    assert {f.division for f in files} == {"E0", "E1"}


def test_both_families_discovered_and_tagged() -> None:
    fetch = _fake_fetch({"englandm.php": ENGLAND_HTML, "argentina.php": ARGENTINA_HTML})
    files = discover_files(fetch, base_url=BASE, main_leagues=[ENGLAND], extra_leagues=[ARGENTINA])
    families = {f.family for f in files}
    assert families == {Family.MAIN, Family.EXTRA}
    extra = [f for f in files if f.family is Family.EXTRA]
    assert len(extra) == 1
    assert extra[0].code == "ARG"
    assert extra[0].url == f"{BASE}new/ARG.csv"
    assert extra[0].season is None and extra[0].division is None
    main = [f for f in files if f.family is Family.MAIN]
    assert all(m.season is not None and m.division is not None for m in main)
    assert all(m.code is None for m in main)


def test_main_file_carries_season_and_division_from_url() -> None:
    fetch = _fake_fetch({"englandm.php": ENGLAND_HTML})
    files = discover_files(fetch, base_url=BASE, main_leagues=[ENGLAND], extra_leagues=[])
    by_div = {f.division: f for f in files}
    assert by_div["E0"].season == "2324"
    assert by_div["E1"].season == "2223"
    assert by_div["E0"].url == f"{BASE}mmz4281/2324/E0.csv"

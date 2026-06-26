"""SPIKE (disposable) — link discovery for football-data.co.uk.

Question: can we discover every league + every CSV using the platform's existing
`requests`-only stack, WITHOUT adding BeautifulSoup? (Open question Q1 / H2.)

Approach: fetch data.php, regex out the per-country `*m.php` landing pages, then fetch
each landing page and regex out the `.csv` links. Characterise counts + URL shapes.
Writes a JSON summary + the raw discovered link list to ../evidence/.

Run: uv run python investigations/football-data-co-uk-ingestion/code/spike1_discover.py
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests

BASE = "https://www.football-data.co.uk/"
EVIDENCE = Path(__file__).resolve().parent.parent / "evidence"
HEADERS = {"User-Agent": "data-platform-investigation-spike/0.1 (+local research)"}

HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def fetch(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def hrefs(html: str) -> list[str]:
    return HREF_RE.findall(html)


def main() -> None:
    EVIDENCE.mkdir(parents=True, exist_ok=True)

    main_html = fetch(urljoin(BASE, "data.php"))
    country_pages = sorted({h for h in hrefs(main_html) if h.endswith("m.php") and h != "data.php"})
    print(f"country landing pages (*m.php): {len(country_pages)}")
    print("  sample:", country_pages[:10])

    summary: dict = {"base": BASE, "country_pages": country_pages, "leagues": {}}
    total_csv = 0

    for page in country_pages:
        try:
            html = fetch(urljoin(BASE, page))
        except Exception as e:  # noqa: BLE001 - spike: record + continue
            summary["leagues"][page] = {"error": str(e)}
            print(f"  ! {page}: {e}")
            continue
        csvs = sorted({h for h in hrefs(html) if h.lower().endswith(".csv")})
        total_csv += len(csvs)
        summary["leagues"][page] = {"csv_count": len(csvs), "csv_sample": csvs[:5]}
        print(f"  {page:<22} {len(csvs):>4} csv files")
        time.sleep(0.4)  # polite throttle

    summary["total_csv_files"] = total_csv
    print(f"\nTOTAL csv files across all leagues: {total_csv}")

    out = EVIDENCE / "spike1_discovery.json"
    out.write_text(json.dumps(summary, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()

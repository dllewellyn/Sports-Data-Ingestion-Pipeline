# Spikes (disposable)

Throwaway experimental code only. **Never imported by production code.** These exist to
produce evidence for `../findings.md`, then get thrown away or rewritten under the
Specification phase.

| Spike | Purpose | What it proves |
| --- | --- | --- |
| `spike1_discover.py` | Link discovery with requests-only | No BeautifulSoup needed; 11 main leagues / ~689 files; `*m.php` filter is buggy and drops 19 extra leagues |
| `spike2_schema_and_parquet.py` | Schema-drift map + validated bronze Parquet | Columns drift 7→106; stable 7-field core; two families; sparse-core + Pandera `strict=False` validates cleanly |

Run spikes from the repo root with the project venv, e.g.:

```bash
uv run python investigations/football-data-co-uk-ingestion/code/<spike>.py
```

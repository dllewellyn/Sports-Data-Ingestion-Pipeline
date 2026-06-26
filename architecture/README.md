# Architecture

C4-model diagrams for the data-ingestion platform, authored as
[Mermaid](https://mermaid.js.org/) `C4Component` diagrams embedded in Markdown.
Mermaid is self-contained — no external macros — so these render **fully offline**
and preview natively on GitHub.

| File | C4 level | Scope |
| --- | --- | --- |
| `c3_data_platform_components.md` | **C3 – Component** | Current Dagster code location (`src/data_platform`): the bronze ingest edge, Pydantic/Pandera validation, the dbt assets + `BronzeAwareTranslator`, and the gold publish asset, plus DuckDB, the Parquet lake, the source API and OpenTelemetry. |
| `football-data-ingestion.md` | **C3 – Component** | Proposed football-data.co.uk bronze ingestion pipeline (from `investigations/football-data-co-uk-ingestion/`). |

C1 (System Context) and C2 (Container) diagrams can be added here later as
`c1_*.md` / `c2_*.md`.

## Rendering (offline)

The diagrams live inside fenced ` ```mermaid ` blocks, so they render with zero
tooling on GitHub or any Mermaid-aware Markdown viewer.

To export an image locally with the Mermaid CLI:

```bash
# one-time: npm i -g @mermaid-js/mermaid-cli
mmdc -i architecture/c3_data_platform_components.md -o c3_data_platform_components.png
```

Rendered PNG/SVG output is intentionally **not** committed — only the Markdown
sources are.

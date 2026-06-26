# Component diagram — football-data.co.uk Bronze Ingestion

> C4 Level 3 component view of the proposed football-data.co.uk bronze ingestion pipeline.
> Findings: `investigations/football-data-co-uk-ingestion/findings.md`
> Decisions: `investigations/football-data-co-uk-ingestion/decisions.md`

```mermaid
C4Component
    title Component diagram — football-data.co.uk Bronze Ingestion

    Person(operator, "Data Operator", "Triggers backfill / incremental runs via the Dagster UI")

    System_Ext(fdcu_main, "football-data.co.uk (main leagues)", "HTTP — mmz4281/<season>/<div>.csv | latin-1, one season×division per file | ~689 files across 11 leagues")
    System_Ext(fdcu_extra, "football-data.co.uk (extra leagues)", "HTTP — new/<CODE>.csv | utf-8-sig, all seasons per file | 19+ leagues (ARG, USA, ...)")

    ContainerDb(parquet_lake, "Parquet Lake", "Parquet files on disk (DATA_DIR)", "Bronze layer: data/bronze/football_main/ and data/bronze/football_extra/")
    Container(dbt_project, "dbt Project (data_platform)", "dbt-duckdb", "Downstream silver/gold models unify or keep the two families as separate marts")

    Container_Boundary(ingestion, "Football Ingestion (Dagster code location)") {
        Component(definitions, "Dagster Definitions", "Python / Dagster", "Registers football_main_bronze and football_extra_bronze assets, backfill / incremental schedule, and shared throttled HTTP resource")

        Component(league_registry, "League Registry", "Python / config (YAML or dict)", "Known whitelist of main leagues (11 country codes) and extra league codes (19+). Drives discovery; prevents noise matches (D6)")

        Component(link_discoverer, "Link Discoverer", "Python / requests + regex", "GETs data.php; regex-extracts per-league page links from the registry whitelist. Handles both main (mmz4281) and extra (new/) URL shapes. No BeautifulSoup required (D3)")

        Component(throttled_http, "Throttled HTTP Client", "Python / requests", "Shared session with 0.4 s/req delay, on-disk skip-existing cache for historical (immutable) files. Re-fetches current season unconditionally (D6, open Q4)")

        Component(main_ingestor, "Main Family Ingestor", "Python / Dagster asset", "Reads latin-1 CSV per season×division file. Validates mandatory 7-field core (Div, Date, HomeTeam, AwayTeam, FTHG, FTAG, FTR) via Pydantic; optional odds/stats columns pass through Pandera strict=False. Emits one Parquet per source file (D4, D5)")

        Component(extra_ingestor, "Extra Family Ingestor", "Python / Dagster asset", "Reads utf-8-sig CSV per league code (multi-season file). Validates different 9-field core (Country, League, Season, Date, Home, Away, HG, AG, Res) via Pydantic. Pandera strict=False for optional odds columns (D5)")

        Component(main_pydantic, "MainMatchRecord schema", "Python / Pydantic v2", "Per-record edge validation for main family. Rejects blank/footer rows — spike proved ~90 rows dropped from 1993/94 E0 correctly (462/552 valid)")

        Component(extra_pydantic, "ExtraMatchRecord schema", "Python / Pydantic v2", "Per-record edge validation for extra family. Different mandatory fields; Season column carried in-file (not from URL path)")

        Component(bronze_frame_schema, "BronzeMatchFrame schema", "Python / Pandera", "Frame-level validation with strict=False — accepts the full sparse 100+ column union without requiring every optional column to be present")
    }

    Rel(operator, definitions, "Triggers jobs / browses assets", "Dagster UI")

    Rel(definitions, league_registry, "Provides league whitelist to")
    Rel(definitions, link_discoverer, "Registers as resource")
    Rel(definitions, main_ingestor, "Registers football_main_bronze asset")
    Rel(definitions, extra_ingestor, "Registers football_extra_bronze asset")

    Rel(link_discoverer, league_registry, "Reads league whitelist")
    Rel(link_discoverer, throttled_http, "Issues page GETs via")
    Rel(link_discoverer, fdcu_main, "Discovers main-family CSV URLs", "HTTPS")
    Rel(link_discoverer, fdcu_extra, "Discovers extra-family CSV URLs", "HTTPS")

    Rel(main_ingestor, throttled_http, "Downloads CSV files via")
    Rel(main_ingestor, fdcu_main, "Fetches mmz4281/<season>/<div>.csv", "HTTPS")
    Rel(main_ingestor, main_pydantic, "Validates each row")
    Rel(main_ingestor, bronze_frame_schema, "Validates assembled frame")
    Rel(main_ingestor, parquet_lake, "Writes bronze/football_main/<league>/<season>/<div>.parquet")

    Rel(extra_ingestor, throttled_http, "Downloads CSV files via")
    Rel(extra_ingestor, fdcu_extra, "Fetches new/<CODE>.csv", "HTTPS")
    Rel(extra_ingestor, extra_pydantic, "Validates each row")
    Rel(extra_ingestor, bronze_frame_schema, "Validates assembled frame")
    Rel(extra_ingestor, parquet_lake, "Writes bronze/football_extra/<code>.parquet")

    Rel(dbt_project, parquet_lake, "Reads football bronze Parquet as external source")
```

"""Dagster code location: assets, resources, and orchestration."""

from __future__ import annotations

from dagster import (
    AssetKey,
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    define_asset_job,
)
from dagster_dbt import DbtCliResource

from .assets.dbt import dbt_models, dbt_project
from .assets.ingestion.espn import espn_bronze
from .assets.ingestion.football_extra import football_extra
from .assets.ingestion.football_main import football_main
from .assets.ingestion.matchbook_events import matchbook_events_bronze
from .assets.ingestion.matchbook_odds import matchbook_odds_bronze, odds_stream_fresh
from .assets.intermediate.matchbook_conform import matchbook_conform
from .assets.intermediate.matchbook_t60 import matchbook_t60_enrichment
from .espn.http_client import ThrottledHttpClient as EspnThrottledHttpClient
from .football.http_client import ThrottledHttpClient
from .otel import configure_telemetry

# Install tracing as soon as the code location is imported (covers both the
# webserver process and every run subprocess).
configure_telemetry()

# Football bronze assets: separate, on-demand source (full backfill is ~705 files).
football_assets = AssetSelection.assets(football_main, football_extra)

# ESPN soccer flow: end-to-end source (bronze scoreboards -> dbt staging +
# intermediate conform + link models). Run via the dedicated `espn_job`. The dbt model
# AssetKeys are `["staging","<model>"]` for staging and `["intermediate","<model>"]` for
# intermediate (verified from the manifest); the `team_aliases` seed surfaces as
# `["staging","team_aliases"]`, so it rides with this source.
#
# int_league/int_season/int_team/int_match are SHARED canonical models, not ESPN's —
# they union every provider's contributions (Spec 012). They're included here because
# ESPN's own bronze scoreboards feed them directly via ref(); they're ALSO included in
# `matchbook_assets` below, since Matchbook mints into them too. Both jobs rebuild the
# same underlying dbt models; that's intentional, not duplication to clean up.
#
# The four canonical_*_export marts also rebuild here, not in matchbook_assets:
# matchbook_conform reads those exports as INPUT (deps=[...] below), and the exports
# themselves ref() the canonical models — including them in the SAME job as
# matchbook_conform would close a cycle (export -> int_match -> matchbook_conform ->
# export) once int_match also depends on matchbook_conform. Rebuilding them here
# instead means matchbook_job always reads exports from the most recent espn_job run
# (at most ~15 minutes stale, given the schedule offset below) rather than needing a
# same-run refresh; matchbook_conform's re-mint-if-still-missing behaviour is already
# idempotent (same deterministic id), so a few extra minutes of export staleness is
# harmless.
espn_assets = AssetSelection.assets(
    espn_bronze,
    AssetKey(["staging", "stg_espn_events"]),
    AssetKey(["intermediate", "int_league"]),
    AssetKey(["intermediate", "int_season"]),
    AssetKey(["intermediate", "int_team"]),
    AssetKey(["intermediate", "int_match"]),
    AssetKey(["intermediate", "int_espn_match_link"]),
    AssetKey(["staging", "team_aliases"]),
    AssetKey(["marts", "canonical_match_export"]),
    AssetKey(["marts", "canonical_team_export"]),
    AssetKey(["marts", "canonical_league_export"]),
    AssetKey(["marts", "canonical_season_export"]),
)

# Matchbook odds bronze: an observable source asset over the out-of-band
# ingestor daemon's Parquet output. The observe job records freshness (age of
# the newest tick file) and runs the freshness check; it never materializes.
matchbook_odds_observe_assets = AssetSelection.assets(
    matchbook_odds_bronze.key
) | AssetSelection.checks_for_assets(matchbook_odds_bronze.key)

# Matchbook end-to-end flow: bronze events -> conform/mint -> T-60 enrichment -> the
# canonical + link dbt models they feed, all in one job (mirrors espn_assets' shape).
# The canonical models (int_league/season/team/match) now depend on matchbook_conform
# via proper dbt source() edges (see _sources.yml + BronzeAwareTranslator), so
# dagster-dbt automatically sequences them to rebuild AFTER conform + T-60 within this
# single job — no separate, later-scheduled job needed to pick up freshly-minted rows.
# The canonical_*_export marts are deliberately NOT selected here (they rebuild in
# espn_assets instead) — see the comment above espn_assets for why including them
# here would close a dependency cycle back through matchbook_conform.
matchbook_assets = AssetSelection.assets(
    matchbook_events_bronze,
    matchbook_conform,
    matchbook_t60_enrichment,
    AssetKey(["intermediate", "int_league"]),
    AssetKey(["intermediate", "int_season"]),
    AssetKey(["intermediate", "int_team"]),
    AssetKey(["intermediate", "int_match"]),
    AssetKey(["intermediate", "int_matchbook_event_link"]),
    AssetKey(["intermediate", "int_matchbook_team_link"]),
    AssetKey(["intermediate", "int_matchbook_league_link"]),
)


# On-demand backfill of the football-data.co.uk bronze source (both families).
# No schedule: run it manually. Idempotent re-runs skip already-landed historical files
# and always refresh current-season files.
football_backfill_job = define_asset_job(
    name="football_backfill",
    selection=football_assets,
    description="Backfill football-data.co.uk main + extra bronze Parquet over the registry.",
)

# ESPN runs end-to-end on a cadence: the bronze scoreboard ingest plus the dbt staging
# + intermediate conform + link models, so each run lands fresh scoreboards AND re-derives
# the canonical match/link rows. Every 6 hours.
espn_job = define_asset_job(
    name="espn_ingestion",
    selection=espn_assets,
    description="ESPN end-to-end: bronze scoreboards -> dbt staging + intermediate conform + link.",
)

espn_schedule = ScheduleDefinition(
    name="espn_every_6h",
    job=espn_job,
    cron_schedule="0 */6 * * *",
)

# Matchbook odds freshness: observe the daemon's bronze output + run the freshness
# check every 15 minutes. Cheap (stats the newest Parquet file); no materialization.
matchbook_odds_observe_job = define_asset_job(
    name="matchbook_odds_observe",
    selection=matchbook_odds_observe_assets,
    description="Observe matchbook_odds bronze freshness (age of the newest tick Parquet).",
)

matchbook_odds_observe_schedule = ScheduleDefinition(
    name="matchbook_odds_observe_schedule",
    job=matchbook_odds_observe_job,
    cron_schedule="*/15 * * * *",
)

# Matchbook: one end-to-end job, like espn_job — bronze ingest, conform/mint, T-60
# enrichment, and the dbt rebuild of the canonical + link models all run together, so a
# freshly-minted team/league/season/match is visible immediately, not after a separate,
# later-scheduled job.
matchbook_job = define_asset_job(
    name="matchbook_ingestion",
    selection=matchbook_assets,
    description=(
        "Matchbook end-to-end: bronze events -> conform/mint -> T-60 enrichment -> "
        "dbt rebuild of int_league/int_season/int_team/int_match + link models."
    ),
)

matchbook_schedule = ScheduleDefinition(
    name="matchbook_every_6h",
    job=matchbook_job,
    # Offset 15 minutes from espn_schedule (also every 6h, on the hour) so the two
    # jobs don't both fire at the same instant and write to the same DuckLake
    # canonical tables concurrently.
    cron_schedule="15 */6 * * *",
)

defs = Definitions(
    assets=[
        dbt_models,
        football_main,
        football_extra,
        espn_bronze,
        matchbook_events_bronze,
        matchbook_odds_bronze,
        matchbook_conform,
        matchbook_t60_enrichment,
    ],
    asset_checks=[odds_stream_fresh],
    jobs=[
        football_backfill_job,
        espn_job,
        matchbook_job,
        matchbook_odds_observe_job,
    ],
    schedules=[
        espn_schedule,
        matchbook_schedule,
        matchbook_odds_observe_schedule,
    ],
    resources={
        "dbt": DbtCliResource(project_dir=dbt_project),
        "football_http": ThrottledHttpClient(),
        "espn_http": EspnThrottledHttpClient(),
    },
)

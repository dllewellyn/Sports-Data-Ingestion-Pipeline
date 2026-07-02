"""Silver + gold layers, built and tested by dbt on DuckDB.

dbt-duckdb reads the bronze Parquet directly (via an external source), builds the
silver staging view and the gold aggregate table, and runs the dbt tests
(`dbt build` = run + test). Each dbt model/test surfaces as a Dagster asset.
"""

from pathlib import Path

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    DbtProject,
    dbt_assets,
)

# repo root: .../src/data_platform/assets/dbt.py -> parents[3] == project root
DBT_PROJECT_DIR = Path(__file__).resolve().parents[3] / "dbt" / "data_platform"

dbt_project = DbtProject(project_dir=DBT_PROJECT_DIR)
# Generates target/manifest.json during local `dagster dev`; in Docker the
# compose command runs `dbt parse` explicitly before the server starts.
dbt_project.prepare_if_dev()


class BronzeAwareTranslator(DagsterDbtTranslator):
    """Map dbt bronze sources onto their upstream Dagster ingest assets so
    Dagster draws the bronze -> silver -> gold lineage edges."""

    # dbt source name -> upstream Dagster bronze asset key.
    _SOURCE_ASSET_KEYS = {
        "espn_events": AssetKey(["espn_bronze"]),
        # matchbook_odds is produced out-of-band by the matchbook-ingestor daemon;
        # matchbook_odds_bronze is the observable source asset standing in for it.
        "matchbook_odds": AssetKey(["matchbook_odds_bronze"]),
        # matchbook_events is produced by the matchbook_events_bronze Dagster asset.
        "matchbook_events": AssetKey(["matchbook_events_bronze"]),
        # matchbook_resolved_links is produced by the matchbook_conform Python asset (Spec 006)
        "matchbook_resolved_links": AssetKey(["matchbook_conform"]),
        # The four provider-scoped canonical-additions files are all written by the same
        # matchbook_conform asset (Spec 012) — mapping them here is what makes int_league/
        # int_season/int_team/int_match Dagster-visibly depend on it, instead of only being
        # rebuilt incidentally by whichever job also happens to include them.
        "matchbook_canonical_match_additions": AssetKey(["matchbook_conform"]),
        "matchbook_canonical_team_additions": AssetKey(["matchbook_conform"]),
        "matchbook_canonical_league_additions": AssetKey(["matchbook_conform"]),
        "matchbook_canonical_season_additions": AssetKey(["matchbook_conform"]),
        # matchbook_t60_enrichment is produced by the matchbook_t60_enrichment Python asset.
        "matchbook_t60_enrichment": AssetKey(["matchbook_t60_enrichment"]),
    }

    def get_asset_key(self, dbt_resource_props: dict) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source":
            mapped = self._SOURCE_ASSET_KEYS.get(dbt_resource_props["name"])
            if mapped is not None:
                return mapped
        return super().get_asset_key(dbt_resource_props)


# matchbook_conform (Spec 012) legitimately produces five separate bronze sources
# (matchbook_resolved_links + the four canonical-additions files) that all map onto
# the SAME upstream AssetKey — dagster-dbt's default duplicate-asset-key validation
# forbids this unless explicitly allowed for source-only collisions.
_TRANSLATOR_SETTINGS = DagsterDbtTranslatorSettings(enable_duplicate_source_asset_keys=True)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=BronzeAwareTranslator(settings=_TRANSLATOR_SETTINGS),
)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    # `build` = run models + run tests, so data validation happens inline.
    yield from dbt.cli(["build"], context=context).stream()

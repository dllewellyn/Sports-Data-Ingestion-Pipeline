"""Silver + gold layers, built and tested by dbt on DuckDB.

dbt-duckdb reads the bronze Parquet directly (via an external source), builds the
silver staging view and the gold aggregate table, and runs the dbt tests
(`dbt build` = run + test). Each dbt model/test surfaces as a Dagster asset.
"""

from pathlib import Path

from dagster import AssetExecutionContext, AssetKey
from dagster_dbt import (
    DagsterDbtTranslator,
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
    """Map the dbt source `bronze.users` onto the upstream `raw_users` asset
    so Dagster draws the bronze -> silver -> gold lineage edge."""

    def get_asset_key(self, dbt_resource_props: dict) -> AssetKey:
        if dbt_resource_props["resource_type"] == "source" and (
            dbt_resource_props["name"] == "users"
        ):
            return AssetKey(["raw_users"])
        return super().get_asset_key(dbt_resource_props)


@dbt_assets(
    manifest=dbt_project.manifest_path,
    dagster_dbt_translator=BronzeAwareTranslator(),
)
def dbt_models(context: AssetExecutionContext, dbt: DbtCliResource):
    # `build` = run models + run tests, so data validation happens inline.
    yield from dbt.cli(["build"], context=context).stream()

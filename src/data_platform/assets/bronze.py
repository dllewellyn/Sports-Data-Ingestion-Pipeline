"""Bronze layer: raw ingest.

Pull from the source API (instrumented `requests`), validate every record with
Pydantic, validate the assembled frame with Pandera, then land it as Parquet.
This is the only asset that touches the outside world.
"""

import pandas as pd
import requests
from dagster import AssetKey, MaterializeResult, MetadataValue, asset

from ..config import settings
from ..models.schemas import User
from ..models.validation import bronze_users_schema
from ..otel import get_tracer


@asset(
    key=AssetKey(["raw_users"]),
    group_name="bronze",
    compute_kind="python",
    description="Raw users pulled from the source API, validated and landed as Parquet.",
)
def raw_users() -> MaterializeResult:
    tracer = get_tracer()
    with tracer.start_as_current_span("ingest.raw_users") as span:
        url = f"{settings.api_base_url}/users"
        span.set_attribute("http.url", url)

        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        # Edge validation: each record must satisfy the Pydantic contract.
        users = [User.model_validate(item) for item in resp.json()]
        span.set_attribute("ingest.record_count", len(users))

        df = pd.DataFrame([u.to_flat() for u in users])

        # Frame validation: dtypes / nullability / ranges before persisting.
        df = bronze_users_schema.validate(df)

        settings.bronze_dir.mkdir(parents=True, exist_ok=True)
        out_path = settings.bronze_dir / "users.parquet"
        df.to_parquet(out_path, index=False)
        span.set_attribute("output.path", str(out_path))
        span.set_attribute("output.rows", len(df))

    return MaterializeResult(
        metadata={
            "record_count": MetadataValue.int(len(df)),
            "path": MetadataValue.path(str(out_path)),
            "columns": MetadataValue.json(list(df.columns)),
            "preview": MetadataValue.md(df.head().to_markdown(index=False)),
        }
    )

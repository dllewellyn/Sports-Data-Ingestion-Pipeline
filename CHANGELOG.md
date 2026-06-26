---
type: OKF Changelog
title: Knowledge Changelog
description: Per-commit record of added and changed knowledge materials, extracted by the .agents pipeline.
timestamp: 2026-06-26T00:00:00Z
---

## 8c8290a — docs: add football-data.co.uk bronze ingestion investigation
<!-- okf:commit=8c8290a -->

- **Commit:** `8c8290aeb3f3a259cd83936066b845fc57eb83b6`
- **Author:** dllewellyn
- **Date:** 2026-06-26T15:35:15+01:00
- **Message:** docs: add football-data.co.uk bronze ingestion investigation

### Created materials

#### `architecture/football-data-ingestion.md`
- **Name:** football-data-ingestion
- **Date:** 2026-06-26T15:35:15+01:00
- **New requirements extracted:**
  - Shared throttled HTTP behavior is required across discovery and ingestion requests, with a fixed delay of 0.4 seconds per request.
  - Both main-family and extra-family ingestion paths are required, with explicit Bronze Parquet write paths for each family.
  - Downstream dbt consumption from football Bronze Parquet external sources is required.
- **Architecture evolution notes:**
  - Introduces a target architecture that extends the platform from generic bronze ingestion into dedicated football ingestion components: registry, link discovery, shared throttled client, and split main/extra ingestors.

#### `architecture/c3_data_platform_components.md`
- **Name:** c3_data_platform_components
- **Date:** 2026-06-26T15:35:15+01:00
- **New requirements extracted:**
  - Bronze ingestion must perform layered validation (Pydantic per-record, Pandera frame-level) before writing Parquet.
  - dbt execution must include a lineage dependency from dbt assets to the bronze `raw_users` asset key.
  - Telemetry must export OTLP spans from platform instrumentation to an OTEL collector.
- **Architecture evolution notes:**
  - Establishes a concrete baseline C3 component map spanning Dagster orchestration, validation components, dbt lineage, DuckDB ownership boundaries, and telemetry export relationships.

#### `architecture/README.md`
- **Name:** README
- **Date:** 2026-06-26T15:35:15+01:00
- **New requirements extracted:**
  - Architecture diagrams should be authored as Mermaid C4Component blocks embedded in Markdown.
  - Rendered image artifacts should not be committed; Markdown sources are the repository source of truth.
- **Architecture evolution notes:**
  - Defines documentation-process baseline with current C3 coverage and explicitly identifies C1/C2 expansion as the next architectural documentation evolution.

No knowledge materials changed in this commit.

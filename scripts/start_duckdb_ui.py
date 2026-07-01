#!/usr/bin/env python3
"""Start the DuckDB built-in web UI connected to the DuckLake catalog."""

import os
import time

import duckdb

POSTGRES_CATALOG_URL = os.environ["POSTGRES_CATALOG_URL"]
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")

con = duckdb.connect()
con.execute(f"ATTACH 'ducklake:{POSTGRES_CATALOG_URL}' AS lake (DATA_PATH '{DATA_DIR}')")
con.execute("INSTALL ui; LOAD ui")
con.execute("CALL start_ui(open := false, host := '0.0.0.0', port := 4213)")

# Block so the container stays alive while the UI web server runs in the background.
while True:
    time.sleep(3600)

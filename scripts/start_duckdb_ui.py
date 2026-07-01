#!/usr/bin/env python3
"""Start the DuckDB built-in web UI connected to the DuckLake catalog."""

import os
import time

import duckdb

POSTGRES_CATALOG_URL = os.environ["POSTGRES_CATALOG_URL"]

con = duckdb.connect()
# No DATA_PATH — DuckLake reads the registered path from the PostgreSQL catalog.
con.execute(f"ATTACH 'ducklake:{POSTGRES_CATALOG_URL}' AS lake")
con.execute("INSTALL ui; LOAD ui")
con.execute("CALL start_ui()")

# Block so the container stays alive while the UI web server runs in the background.
while True:
    time.sleep(3600)

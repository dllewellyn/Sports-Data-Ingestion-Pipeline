#!/usr/bin/env python3
"""Start the DuckDB built-in web UI connected to the DuckLake catalog.

start_ui() binds only to localhost inside the container. A lightweight
TCP proxy (Python socketserver) forwards 0.0.0.0:4213 -> localhost:4213
so the UI is reachable from outside via Docker's port mapping.
"""

import os
import socket
import socketserver
import threading
import time

import duckdb

POSTGRES_CATALOG_URL = os.environ["POSTGRES_CATALOG_URL"]
DUCKDB_UI_INTERNAL_PORT = 4213
PROXY_PORT = 4214  # exposed by Docker on the host as 4213


class _ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            with socket.create_connection(("localhost", DUCKDB_UI_INTERNAL_PORT)) as srv:
                self.request.setblocking(False)
                srv.setblocking(False)
                while True:
                    try:
                        data = self.request.recv(4096)
                        if data:
                            srv.sendall(data)
                        else:
                            break
                    except BlockingIOError:
                        pass
                    try:
                        data = srv.recv(4096)
                        if data:
                            self.request.sendall(data)
                        elif data == b"":
                            break
                    except BlockingIOError:
                        pass
        except Exception:
            pass


def _start_proxy() -> None:
    with socketserver.ThreadingTCPServer(("0.0.0.0", PROXY_PORT), _ForwardHandler) as srv:
        srv.allow_reuse_address = True
        srv.serve_forever()


con = duckdb.connect()
# No DATA_PATH — DuckLake reads the registered path from the PostgreSQL catalog.
con.execute(f"ATTACH 'ducklake:{POSTGRES_CATALOG_URL}' AS lake")
con.execute("INSTALL ui; LOAD ui")
con.execute("CALL start_ui()")

# Give the UI server a moment to bind to localhost:4213.
time.sleep(2)

# Forward 0.0.0.0:4214 -> localhost:4213 so the Docker port mapping works.
threading.Thread(target=_start_proxy, daemon=True).start()

while True:
    time.sleep(3600)

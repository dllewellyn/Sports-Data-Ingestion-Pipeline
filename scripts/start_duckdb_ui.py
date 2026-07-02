#!/usr/bin/env python3
"""Start the DuckDB built-in web UI connected to the DuckLake catalog.

start_ui() binds the UI's HTTP server to localhost inside the container (there is
no host/bind-address setting — only `ui_local_port`), so Docker's port mapping,
which forwards from the container's external interface, can't reach it directly.
A small TCP relay forwards 0.0.0.0:4214 -> localhost:4213 to bridge that gap; the
compose port mapping exposes 4214 on the host.

The relay uses one blocking pump thread per direction per connection. That handles
what a browser actually does — many parallel keep-alive connections plus the UI's
long-lived backend polling channel — which the previous single non-blocking
busy-loop could not (it served one sequential request fine but spun/stalled under
real concurrency, leaving the UI a blank white screen).
"""

import contextlib
import os
import socket
import socketserver
import threading
import time

import duckdb

POSTGRES_CATALOG_URL = os.environ["POSTGRES_CATALOG_URL"]
DUCKDB_UI_INTERNAL_PORT = 4213
PROXY_PORT = 4214  # exposed by Docker on the host as 4213
BUF = 65536


def _pump(src: socket.socket, dst: socket.socket) -> None:
    """Copy bytes src -> dst until EOF, then half-close dst's write side so the
    peer sees the end of stream. Blocking; no busy-loop."""
    try:
        while True:
            data = src.recv(BUF)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        with contextlib.suppress(OSError):
            dst.shutdown(socket.SHUT_WR)


class _ForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        try:
            upstream = socket.create_connection(("localhost", DUCKDB_UI_INTERNAL_PORT))
        except OSError:
            return
        with upstream:
            client = self.request
            # This handler already runs in its own thread; spawn one more for the
            # reverse direction and pump the forward direction here.
            reverse = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
            reverse.start()
            _pump(client, upstream)
            reverse.join()


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def _start_proxy() -> None:
    with _ProxyServer(("0.0.0.0", PROXY_PORT), _ForwardHandler) as srv:
        srv.serve_forever()


# The UI's primary connection is a small PERSISTENT file, not ":memory:". The
# DuckDB Local UI persists its "app state" (notebooks, settings, the local user
# record) into its primary database; against a pure in-memory instance it has
# nowhere to initialise that store and fails in the browser with
# "Failed to resolve app state with user - RangeError: Offset is outside the
# bounds of the DataView". This file is opened ONLY by the duckdb-ui service, so
# it does NOT reintroduce the warehouse.duckdb single-writer lock problem (nothing
# else touches it). The DuckLake catalog `lake` is attached as a secondary DB so
# the pipeline data is still browsable.
con = duckdb.connect("/app/data/ui_state.duckdb")
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

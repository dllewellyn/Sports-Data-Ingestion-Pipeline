import contextlib
import logging
import socket
import threading

import duckdb

from data_platform.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("duckdb_ui")


def proxy_stream(src: socket.socket, dst: socket.socket) -> None:
    try:
        while buf := src.recv(65536):
            dst.sendall(buf)
    except Exception:
        pass
    finally:
        with contextlib.suppress(Exception):
            dst.shutdown(socket.SHUT_WR)


def main() -> None:
    logger.info("Initializing DuckDB UI catalog attachments...")
    conn = duckdb.connect()
    conn.execute("INSTALL ui; LOAD ui;")
    conn.execute("INSTALL postgres; LOAD postgres;")
    conn.execute("INSTALL ducklake; LOAD ducklake;")

    warehouse_path = settings.duckdb_path
    if warehouse_path.exists():
        logger.info(f"Attaching warehouse at {warehouse_path} (READ_ONLY)")
        conn.execute(f"ATTACH '{warehouse_path}' AS warehouse (READ_ONLY);")

    catalog_url = settings.postgres_catalog_url
    lake_path = settings.ducklake_data_path.resolve()
    logger.info(f"Attaching DuckLake catalog with data path {lake_path}...")
    conn.execute(
        f"ATTACH 'ducklake:{catalog_url}' AS lake "
        f"(DATA_PATH '{lake_path}/', OVERRIDE_DATA_PATH true);"
    )

    logger.info("Starting DuckDB UI server...")
    conn.execute("CALL start_ui();")

    # DuckDB UI listens on localhost:4213. We bind a TCP forwarder on 0.0.0.0:4214
    # so external Docker port mapping can reach it.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 4214))
    srv.listen(50)
    logger.info("TCP forwarder listening on 0.0.0.0:4214 -> localhost:4213")

    while True:
        client_sock, _ = srv.accept()
        try:
            dest_sock = socket.create_connection(("localhost", 4213))
        except Exception as e:
            logger.error(f"Failed to connect to internal DuckDB UI: {e}")
            client_sock.close()
            continue

        def handle_client(c: socket.socket, d: socket.socket) -> None:
            t1 = threading.Thread(target=proxy_stream, args=(c, d))
            t2 = threading.Thread(target=proxy_stream, args=(d, c))
            t1.start()
            t2.start()
            t1.join()
            t2.join()
            with contextlib.suppress(Exception):
                c.close()
            with contextlib.suppress(Exception):
                d.close()

        threading.Thread(target=handle_client, args=(client_sock, dest_sock), daemon=True).start()


if __name__ == "__main__":
    main()

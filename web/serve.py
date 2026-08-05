#!/usr/bin/env python3
"""Start the production server (waitress)."""

import os
import sys

from waitress import serve

from tttool_web.app import create_app
from tttool_web.config import config


def main() -> int:
    host = os.environ.get("TTTOOL_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("TTTOOL_WEB_PORT", "8080"))
    threads = int(os.environ.get("TTTOOL_WEB_THREADS", "4"))
    print(
        f"tttool web on http://{host}:{port}  "
        f"(data: {config.DATA_DIR}, auth: {'on' if config.auth_enabled else 'off'})",
        flush=True,
    )
    serve(
        create_app(),
        host=host,
        port=port,
        threads=threads,
        # Uploads of whole media directories can take a while on slow links.
        channel_timeout=max(config.RUN_TIMEOUT, 120),
        ident="tttool-web",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""`python -m researchly_service` — run the engine with uvicorn.

Listens on 0.0.0.0:$PORT (Cloud Run convention; default 8080). uvicorn's
own logging config is NOT used (log_config=None) and its access log is off:
logging_setup routes everything through one JSON handler that cannot carry
document text, and the access line comes from the request middleware.
"""

from __future__ import annotations

import os

import uvicorn

from . import logging_setup


def main() -> None:
    logging_setup.setup()
    uvicorn.run(
        "researchly_service.main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8080")),
        log_config=None,
        access_log=False,
        # X-Forwarded-For is interpreted by the rate limiter itself
        # (RESEARCHLY_TRUSTED_PROXY_HOPS); uvicorn must not rewrite it.
        proxy_headers=False,
        server_header=False,
        workers=1,              # one engine per process; scale with instances
        timeout_keep_alive=30,
    )


if __name__ == "__main__":
    main()

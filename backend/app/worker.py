"""arq worker entrypoint.

Run with:  python -m app.worker   (from backend/)

The worker processes process_incoming_message and send_outgoing jobs.
All logging goes to stdout so Railway/docker can capture it.
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s — %(message)s",
    stream=sys.stdout,
)

from arq import run_worker

from app.intake.queue import WorkerSettings

if __name__ == "__main__":
    run_worker(WorkerSettings)

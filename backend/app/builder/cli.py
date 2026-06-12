"""Builder CLI: python -m app.builder.cli --tenant <id> --assets <dir> [--dry-run]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


async def _run(tenant_id: str, assets_dir: Path, dry_run: bool) -> int:
    from app.builder.agent import run_build

    report = await run_build(tenant_id=tenant_id, assets_dir=assets_dir, dry_run=dry_run)
    print()
    print(report.to_text())
    passed = report.self_test.get("passed", False)
    return 0 if passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the WhatsBase Builder agent")
    parser.add_argument("--tenant", required=True, help="Tenant UUID")
    parser.add_argument("--assets", required=True, help="Path to assets directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run LLM calls but skip Storage uploads and DB writes")
    args = parser.parse_args()

    _setup_logging()

    assets_dir = Path(args.assets).resolve()
    if not assets_dir.exists():
        print(f"ERROR: assets directory not found: {assets_dir}", file=sys.stderr)
        sys.exit(1)

    exit_code = 1
    try:
        exit_code = asyncio.run(_run(args.tenant, assets_dir, args.dry_run))
    finally:
        # Flush Langfuse batched events before the process exits.
        from app.core.observability import get_langfuse
        lf = get_langfuse()
        if lf is not None:
            lf.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

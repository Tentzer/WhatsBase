"""Quick smoke test: emit one trace and confirm the Langfuse v4 wiring works.

Run from backend/:
    python test_langfuse_smoke.py

A trace named 'smoke-test' should appear in the Langfuse dashboard within ~10 s.
Delete this file after verifying.
"""

import asyncio
from app.core.observability import get_langfuse, observe, update_trace


@observe(name="smoke-test")
async def _emit():
    update_trace(tenant_id="smoke", note="v4-wiring-check")
    return "ok"


async def main():
    result = await _emit()
    print(f"Function returned: {result}")
    lf = get_langfuse()
    if lf:
        lf.shutdown()
        print("Langfuse shutdown complete — check dashboard for 'smoke-test' trace.")
    else:
        print("Langfuse client is None — check .env for LANGFUSE_PUBLIC_KEY / SECRET_KEY.")


asyncio.run(main())

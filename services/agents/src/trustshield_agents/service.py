"""Public entry point for the gateway: evaluate_payment(req) -> PaymentRiskResponse."""

from __future__ import annotations

import asyncio
import concurrent.futures
import uuid

from google.adk.runners import InMemoryRunner
from google.genai import types
from trustshield_contracts import PaymentRiskRequest, PaymentRiskResponse

from .adapters.factory import Services, build_services
from .orchestrator import WORKFLOW_NAME, build_workflow
from .settings import mode

_workflows: dict[int, object] = {}


def _workflow_for(services: Services):
    key = id(services)
    if key not in _workflows:
        _workflows[key] = build_workflow(services)
    return _workflows[key]


async def evaluate_payment_async(
    req: PaymentRiskRequest, services: Services | None = None
) -> PaymentRiskResponse:
    """Run the orchestrator workflow for one payment. Leaves audit_id / case_id empty."""
    svc = services or build_services()
    runner = InMemoryRunner(agent=_workflow_for(svc), app_name=WORKFLOW_NAME)
    try:
        session = await runner.session_service.create_session(
            app_name=WORKFLOW_NAME, user_id=req.payer_id, session_id=uuid.uuid4().hex
        )
        message = types.Content(role="user", parts=[types.Part(text=req.model_dump_json())])
        final: dict | None = None
        async for event in runner.run_async(
            user_id=req.payer_id, session_id=session.id, new_message=message
        ):
            out = event.output
            if isinstance(out, dict) and "decision" in out and "risk_score" in out:
                final = out
    finally:
        await runner.close()
    if final is None:
        raise RuntimeError("orchestrator finished without a decision")
    return PaymentRiskResponse.model_validate(final)


def evaluate_payment(req: PaymentRiskRequest) -> PaymentRiskResponse:
    """Synchronous wrapper. Safe to call from sync code or from inside a running event loop
    (e.g. a FastAPI `async def` handler), where it runs on a worker thread.
    In async code prefer `await evaluate_payment_async(req)`."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(evaluate_payment_async(req))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, evaluate_payment_async(req)).result()


async def warm_up_async() -> None:
    """Do the one-off start-up work before the first payment arrives.

    Builds the adapters (in gcp mode this resolves credentials, ~1 s), compiles the workflow and
    opens the Gemini connections with a free metadata call. Call it from the gateway's start-up,
    in the same event loop that will serve requests. Raises if gcp mode is misconfigured, so a
    bad deploy fails at start-up instead of on the first payment.
    """
    svc = build_services()
    _workflow_for(svc)
    if svc.gemini is not None:
        await svc.gemini.warm_up()


def warm_up() -> None:
    """Synchronous :func:`warm_up_async` for scripts. Async callers should await the async one."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(warm_up_async())
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(asyncio.run, warm_up_async()).result()


__all__ = ["evaluate_payment", "evaluate_payment_async", "mode", "warm_up", "warm_up_async"]

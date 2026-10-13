"""TrustShield Orchestrator as an ADK graph Workflow.

    START -> parse_request -> (transaction_risk || scam_context) -> join_signals -> fuse_decision

ADK 2.x deprecates SequentialAgent / ParallelAgent in favour of Workflow; a tuple in an edge
chain fans out in parallel and JoinNode waits for all branches. Governance and audit logging are
NOT done here: the gateway owns them.
"""

from __future__ import annotations

import asyncio
import json

from google.adk import Workflow
from google.adk.workflow import JoinNode
from google.genai import types
from trustshield_contracts import PaymentRiskRequest
from trustshield_contracts.fixtures import DEMO1_PAYMENT, load_fixture

from .adapters.factory import Services, build_services
from .fusion import fuse
from .ports import PayeeFeatures, PayerFeatures, ScamAssessment
from .risk import RiskConfig

WORKFLOW_NAME = "trustshield_orchestrator"


def _to_request(node_input: object) -> PaymentRiskRequest:
    """Accept a request model/dict, or chat text from `adk web`.

    In `adk web`, send the request JSON, or any plain text to run the ₹85k demo payment with
    that text as message_context ("demo1" runs the fixture unchanged).
    """
    if isinstance(node_input, PaymentRiskRequest):
        return node_input
    if isinstance(node_input, dict):
        return PaymentRiskRequest.model_validate(node_input)
    if isinstance(node_input, types.Content):
        text = "".join(p.text or "" for p in node_input.parts or []).strip()
    else:
        text = str(node_input or "").strip()
    try:
        return PaymentRiskRequest.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValueError):
        demo = load_fixture(DEMO1_PAYMENT)["request"]
        if text and text.lower() != "demo1":
            demo["message_context"] = text
        return PaymentRiskRequest.model_validate(demo)


def build_workflow(services: Services | None = None, cfg: RiskConfig | None = None) -> Workflow:
    svc = services or build_services()

    def parse_request(ctx, node_input) -> dict:
        req = _to_request(node_input)
        ctx.state["request"] = req.model_dump(mode="json")
        return ctx.state["request"]

    async def transaction_risk(node_input: dict) -> dict:
        """Transaction Risk agent: behavioural features from the FeatureStore port."""
        req = PaymentRiskRequest.model_validate(node_input)
        payer, payee = await asyncio.gather(
            svc.features.payer(req.payer_id), svc.features.payee(req.payee_vpa)
        )
        return {"payer": payer.model_dump(mode="json"), "payee": payee.model_dump(mode="json")}

    async def scam_context(node_input: dict) -> dict:
        """Scam Context agent: Gemini (gcp) or rules (mock) on message_context."""
        req = PaymentRiskRequest.model_validate(node_input)
        # TODO: attachment_uri (screenshot / QR / transcript) -> Gemini multimodal, async path.
        assessment = await svc.scam.classify(req.message_context or "")
        return {**assessment.model_dump(mode="json"), "classifier": svc.scam.name}

    async def fuse_decision(ctx, node_input: dict) -> dict:
        req = PaymentRiskRequest.model_validate(ctx.state["request"])
        tx = node_input["transaction_risk"]
        response = await fuse(
            req,
            PayerFeatures.model_validate(tx["payer"]),
            PayeeFeatures.model_validate(tx["payee"]),
            ScamAssessment.model_validate(node_input["scam_context"]),
            svc,
            cfg,
        )
        return response.model_dump(mode="json")

    return Workflow(
        name=WORKFLOW_NAME,
        description="Scores a UPI payment: transaction risk + scam context in parallel, fused into R.",
        edges=[
            (
                "START",
                parse_request,
                (transaction_risk, scam_context),
                JoinNode(name="join_signals"),
                fuse_decision,
            )
        ],
    )

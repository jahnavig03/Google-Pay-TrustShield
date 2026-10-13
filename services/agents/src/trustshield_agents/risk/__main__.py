"""python -m trustshield_agents.risk demo  — score the ₹85,000 fixture with the risk engine only."""

from __future__ import annotations

import asyncio
import sys

from trustshield_contracts import PaymentRiskRequest
from trustshield_contracts.fixtures import DEMO1_PAYMENT, load_fixture

from ..adapters.json_feature_store import JsonFeatureStore
from ..adapters.rule_scam_classifier import RuleScamClassifier
from ..fusion import build_risk_inputs
from . import load_risk_config, score


async def _demo() -> None:
    req = PaymentRiskRequest.model_validate(load_fixture(DEMO1_PAYMENT)["request"])
    store = JsonFeatureStore()
    payer, payee = await store.payer(req.payer_id), await store.payee(req.payee_vpa)
    scam = RuleScamClassifier().classify_sync(req.message_context)
    cfg = load_risk_config()
    result = score(build_risk_inputs(req, payer, payee, scam), cfg)

    print(f"Payment {req.transaction_id}: ₹{req.amount:,.0f} -> {req.payee_vpa}")
    print(
        f"  scam context: p={scam.scam_probability} pattern={scam.pattern} cues={scam.manipulation_cues}"
    )
    print("  features x:   " + "  ".join(f"{k}={v:.2f}" for k, v in result.features.items()))
    print("  w·x:          " + "  ".join(f"{k}={v:.2f}" for k, v in result.contributions.items()))
    print(f"  logit = {cfg.bias} + Σ w·x = {result.logit:.2f}")
    print(f"  R = {result.risk_score:.4f}  ->  {result.decision.value}")
    print(f"  analyst_case_required = {result.analyst_case_required}")
    print("  top signals:")
    for s in result.top_signals:
        print(f"    [{s.contribution:>4.2f}] {s.label}: {s.plain_explanation}")


def main(argv: list[str]) -> int:
    if argv[:1] != ["demo"]:
        print("usage: python -m trustshield_agents.risk demo", file=sys.stderr)
        return 2
    asyncio.run(_demo())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

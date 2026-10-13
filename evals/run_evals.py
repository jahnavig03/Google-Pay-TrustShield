"""Run the eval sets through evaluate_payment and report against PRD §2 targets.

    cd services/agents && source .venv/bin/activate
    python ../../evals/run_evals.py [--mode mock|gcp]

Writes evals/results/<YYYY-MM-DD>.md (and prints it).
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime as dt
import json
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tone_checks import check_response

DECISION_RANK = {"ALLOW": 0, "WARN": 1, "STEP_UP_VERIFICATION": 2, "HOLD_AND_ESCALATE": 3}
SCAM_PATTERNS = {
    "urgency",
    "fake_kyc",
    "fake_refund",
    "receive_money_first",
    "impersonation",
    "qr_swap",
}

# Wrapper payment for message-only evals: a usual amount to a long-standing payee, so the
# Scam Context signal is the only thing that varies.
MSG_PAYER = {"median_amount": 2000, "avg_daily_txn": 3, "txn_count_1h": 0, "txn_count_24h": 1}
MSG_PAYEE = {"flags": [], "reported_links": 0, "fan_in_24h": 1, "is_merchant": False}


def load_jsonl(name: str) -> list[dict]:
    with open(HERE / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class ScenarioFeatureStore:
    """Per-scenario features so evals don't depend on data/mock/features.json."""

    def __init__(self, payers: dict, payees: dict):
        from trustshield_agents.ports import PayeeFeatures, PayerFeatures

        self._payers = {k: PayerFeatures.model_validate(v) for k, v in payers.items()}
        self._payees = {k: PayeeFeatures.model_validate(v) for k, v in payees.items()}

    async def payer(self, payer_id):
        return self._payers[payer_id]

    async def payee(self, payee_vpa):
        return self._payees[payee_vpa]


def baseline_flags(req: dict, payer: dict) -> bool:
    """Context-free rules a typical fraud stack uses: big vs median, new payee, new device."""
    median = payer.get("median_amount") or 2000
    return (
        req["amount"] >= 5 * median
        or req["beneficiary_age_minutes"] < 24 * 60
        or req["device_changed"]
    )


def pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{100 * n / d:.0f}% ({n}/{d})"


async def run(mode: str) -> str:
    os.environ["TRUSTSHIELD_MODE"] = mode
    from trustshield_contracts import PaymentRiskRequest

    from trustshield_agents import evaluate_payment_async
    from trustshield_agents.adapters.factory import build_services
    from trustshield_agents.diagnostics import watch_fallbacks

    fallbacks = watch_fallbacks()

    scenarios = load_jsonl("payment_scenarios.jsonl")
    messages = load_jsonl("scam_messages.jsonl")

    payers = {s["request"]["payer_id"]: s["features"]["payer"] for s in scenarios}
    payees = {s["request"]["payee_vpa"]: s["features"]["payee"] for s in scenarios}
    payers["eval_msg_payer"], payees["eval.msg.payee@synthbank"] = MSG_PAYER, MSG_PAYEE
    services = dataclasses.replace(build_services(), features=ScenarioFeatureStore(payers, payees))

    latencies: list[float] = []

    async def call(req: dict) -> dict:
        t0 = time.perf_counter()
        resp = await evaluate_payment_async(PaymentRiskRequest.model_validate(req), services)
        latencies.append((time.perf_counter() - t0) * 1000)
        return resp.model_dump(mode="json")

    await call(scenarios[0]["request"])  # warm-up, not counted
    latencies.clear()

    # ---- payment scenarios ----
    rows = []
    for s in scenarios:
        resp = await call(s["request"])
        rows.append((s, resp))

    def caught(resp, at="WARN"):
        return DECISION_RANK[resp["decision"]] >= DECISION_RANK[at]

    high = [(s, r) for s, r in rows if s["category"] == "high_risk"]
    hard = [(s, r) for s, r in rows if s["category"] == "hard_negative"]
    recall = sum(caught(r) for _, r in high)
    recall_strict = sum(caught(r, "STEP_UP_VERIFICATION") for _, r in high)
    fp_ts = sum(r["decision"] != "ALLOW" for _, r in hard)
    fp_ts_strict = sum(caught(r, "STEP_UP_VERIFICATION") for _, r in hard)
    fp_base = sum(baseline_flags(s["request"], s["features"]["payer"]) for s, _ in hard)
    fp_reduction = "n/a" if fp_base == 0 else f"{100 * (1 - fp_ts / fp_base):.0f}%"
    band_ok = [(s, r) for s, r in rows if r["decision"] in s["expected"]]

    # ---- scam messages ----
    msg_rows = []
    for m in messages:
        req = {
            "transaction_id": f"EVAL-{m['id']}",
            "amount": 2000,
            "payer_id": "eval_msg_payer",
            "payee_vpa": "eval.msg.payee@synthbank",
            "beneficiary_age_minutes": 525600,
            "message_context": m["text"],
        }
        resp = await call(req)
        predicted = resp["risk_type"] if resp["risk_type"] in SCAM_PATTERNS else "none"
        msg_rows.append((m, predicted, resp))
    scam_msgs = [x for x in msg_rows if x[0]["is_scam"]]
    neg_msgs = [x for x in msg_rows if not x[0]["is_scam"]]
    msg_recall = sum(p != "none" for _, p, _ in scam_msgs)
    msg_fp = sum(p != "none" for _, p, _ in neg_msgs)
    pattern_ok = sum(p == m["label"] for m, p, _ in msg_rows)

    # ---- tone, signals, approval ----
    all_resps = [r for _, r in rows] + [r for _, _, r in msg_rows]
    tone = [(r, check_response(r)) for r in all_resps]
    tone_bad = [(r, v) for r, v in tone if v]
    warnings = [r for r in all_resps if r["decision"] != "ALLOW"]
    signals_ok = sum(
        3 <= len(r["top_signals"]) <= 5 and all(s["plain_explanation"] for s in r["top_signals"])
        for r in warnings
    )
    high_impact = [r for r in all_resps if DECISION_RANK[r["decision"]] >= 2]
    case_flagged = sum(r["analyst_case_required"] for r in high_impact)
    evidence_ok = sum(bool(r["evidence_ids"]) for r in all_resps)

    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
    mean = statistics.fmean(latencies)

    def status(ok: bool) -> str:
        return "✅" if ok else "❌"

    today = dt.date.today().isoformat()
    out = [
        f"# TrustShield eval run — {today}",
        "",
        (
            f"Mode: `TRUSTSHIELD_MODE={mode}` · {len(scenarios)} payment scenarios · "
            f"{len(messages)} messages · {len(latencies)} evaluate_payment calls · synthetic data only."
        ),
        "",
        "## PRD §2 targets",
        "",
        "| Metric | Target | Result | |",
        "| --- | --- | --- | --- |",
        (
            f"| Fraud detection recall, synthetic high-risk payments (≥ WARN) | 85–95% | "
            f"{pct(recall, len(high))} | {status(recall / len(high) >= 0.85)} |"
        ),
        (
            f"| False-positive reduction vs context-free rules (hard negatives) | 25–40% | "
            f"{fp_reduction} (TrustShield {fp_ts}/{len(hard)} vs baseline {fp_base}/{len(hard)}) | "
            f"{status(fp_base > 0 and 1 - fp_ts / fp_base >= 0.25)} |"
        ),
        "| Investigation preparation time | 50–70% reduction | not measured (PayInvestigator not built yet) | — |",
        (
            f"| Signals shown per customer warning | Top 3–5, each explained | "
            f"{pct(signals_ok, len(warnings))} of non-ALLOW responses | "
            f"{status(signals_ok == len(warnings))} |"
        ),
        "| Merchant screenshot-fraud detection | ≥ 90% | not measured (PayGuard not built yet) | — |",
        (
            f"| Risk API latency | < 2 s average | mean {mean:.0f} ms · p50 {p50:.0f} ms · p95 {p95:.0f} ms | "
            f"{status(mean < 2000)} |"
        ),
        (
            f"| Human approval on high-impact actions | 100% | {pct(case_flagged, len(high_impact))} of "
            f"STEP_UP/HOLD set analyst_case_required (approval itself enforced by gateway Governance) | "
            f"{status(case_flagged == len(high_impact))} |"
        ),
        "",
        "## Detail",
        "",
        "| Metric | Result |",
        "| --- | --- |",
        f"| High-risk recall, strict (≥ STEP_UP) | {pct(recall_strict, len(high))} |",
        f"| Hard-negative friction (any non-ALLOW) | {pct(fp_ts, len(hard))} |",
        f"| Hard-negative high friction (≥ STEP_UP) | {pct(fp_ts_strict, len(hard))} |",
        f"| Payment decision within expected band | {pct(len(band_ok), len(rows))} |",
        f"| Scam-message recall | {pct(msg_recall, len(scam_msgs))} |",
        f"| Legit-but-urgent messages flagged (FP) | {pct(msg_fp, len(neg_msgs))} |",
        f"| Pattern accuracy (incl. `none` on negatives) | {pct(pattern_ok, len(msg_rows))} |",
        f"| Tone violations | {len(tone_bad)} of {len(tone)} responses |",
        f"| Responses with evidence_ids | {pct(evidence_ok, len(all_resps))} |",
        f"| Gemini fallbacks to rules/templates | {len(fallbacks.messages)} |",
        f"| Gemini call stats | {services.gemini.stats.summary() if services.gemini else 'n/a (mock)'} |",
        "",
    ]

    misses = [(s, r) for s, r in rows if r["decision"] not in s["expected"]]
    if misses:
        out += [
            "## Payment scenarios outside expected band",
            "",
            "| id | category | note | expected | got | R |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        out += [
            f"| {s['id']} | {s['category']} | {s['note']} | {', '.join(s['expected'])} | "
            f"{r['decision']} | {r['risk_score']} |"
            for s, r in misses
        ]
        out.append("")
    wrong = [(m, p) for m, p, _ in msg_rows if p != m["label"]]
    if wrong:
        out += [
            "## Message pattern errors",
            "",
            "| id | lang | label | predicted |",
            "| --- | --- | --- | --- |",
        ]
        out += [f"| {m['id']} | {m['lang']} | {m['label']} | {p} |" for m, p in wrong]
        out.append("")
    if tone_bad:
        out += ["## Tone violations", ""]
        out += [
            f"- `{r['decision']}`: {', '.join(v)} — “{r['customer_message'][:120]}”"
            for r, v in tone_bad
        ]
        out.append("")
    out += [
        "## Method",
        "",
        (
            "- Payment scenarios carry their own payer/payee features (`payment_scenarios.jsonl`), "
            "so results don't depend on `data/mock/features.json`."
        ),
        (
            "- Messages are wrapped in a usual-amount payment to a long-standing payee; the predicted "
            "pattern is the response `risk_type` (anything that is not a scam pattern counts as `none`)."
        ),
        (
            "- Baseline for FP reduction = context-free rules: amount ≥ 5× median, payee < 24 h old, "
            "or new device."
        ),
        (
            "- Latency = wall time of `evaluate_payment_async` (ADK workflow incl. Runner set-up), "
            "after one warm-up call."
        ),
        (
            "- Caveat: the mock-mode keyword rules (`config/scam_rules.yaml`) were tuned while building "
            "this set, so message metrics are optimistic. Re-run with `--mode gcp` and add a held-out "
            "set (e.g. from Ronak's generator) before quoting them."
        ),
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["mock", "gcp"], default=os.environ.get("TRUSTSHIELD_MODE", "mock")
    )
    args = parser.parse_args()
    report = asyncio.run(run(args.mode))
    out_dir = HERE / "results"
    out_dir.mkdir(exist_ok=True)
    path = (
        out_dir
        / f"{dt.date.today().isoformat()}{'' if args.mode == 'mock' else '-' + args.mode}.md"
    )
    path.write_text(report, encoding="utf-8")
    print(report)
    print(f"saved {path}")


if __name__ == "__main__":
    main()

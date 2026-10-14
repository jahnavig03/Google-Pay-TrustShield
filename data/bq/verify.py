"""Check the BigQuery feature views return exactly what features.json holds.

    python data/bq/verify.py [--project ID] [--dataset trustshield]

Dry-runs each view query first and prints the bytes it would process (a few MB; free tier),
then reads both views with the bq CLI and compares every row with
services/agents/data/mock/features.json. Exits 1 on any difference.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FEATURES = REPO / "services" / "agents" / "data" / "mock" / "features.json"


def _env_file_value(key: str) -> str | None:
    env = REPO / ".env"
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].split("#")[0].strip().strip("'\"") or None
    return None


def _bq(project: str, sql: str, *flags: str) -> str:
    exe = shutil.which("bq")
    if not exe:
        sys.exit("bq is not on PATH (install the Google Cloud CLI)")
    # The query goes in on stdin so no shell ever re-parses its quotes or backticks.
    proc = subprocess.run(
        [exe, f"--project_id={project}", "query", "--use_legacy_sql=false", *flags],
        input=sql,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,  # report bq's own error output below
    )
    if proc.returncode != 0:
        sys.exit(f"bq failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def _rows(project: str, view: str) -> list[dict]:
    sql = f"SELECT * FROM `{view}`"
    dry = _bq(project, sql, "--dry_run")
    size = re.search(r"(\d+) bytes", dry)
    print(f"  dry run  {view}: {size.group(1) if size else '?'} bytes")
    out = _bq(project, sql, "--format=json", "--max_rows=1000000", "--quiet")
    return json.loads(out or "[]")


def _num(value) -> float | None:
    return None if value is None else float(value)


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project", default=os.environ.get("GCP_PROJECT_ID") or _env_file_value("GCP_PROJECT_ID")
    )
    parser.add_argument(
        "--dataset",
        default=os.environ.get("BQ_DATASET") or _env_file_value("BQ_DATASET") or "trustshield",
    )
    args = parser.parse_args()
    if not args.project:
        sys.exit("set GCP_PROJECT_ID (env or .env) or pass --project")

    expected = json.loads(FEATURES.read_text(encoding="utf-8"))
    base = f"{args.project}.{args.dataset}"
    problems: list[str] = []

    payers = {r["payer_id"]: r for r in _rows(args.project, f"{base}.v_payer_features")}
    if set(payers) != set(expected["payers"]):
        problems.append(
            f"payer ids differ: view {len(payers)}, features.json {len(expected['payers'])}"
        )
    for key, want in expected["payers"].items():
        got = payers.get(key)
        if got is None:
            continue
        for col in ("median_amount", "avg_daily_txn", "txn_count_1h", "txn_count_24h"):
            if not _same(_num(got[col]), want[col]):
                problems.append(f"payer {key}.{col}: view {got[col]!r} != {want[col]!r}")

    payees = {r["payee_vpa"]: r for r in _rows(args.project, f"{base}.v_payee_features")}
    if set(payees) != set(expected["payees"]):
        problems.append(
            f"payee VPAs differ: view {len(payees)}, features.json {len(expected['payees'])}"
        )
    for key, want in expected["payees"].items():
        got = payees.get(key)
        if got is None:
            continue
        if list(got.get("flags") or []) != want["flags"]:
            problems.append(f"payee {key}.flags: view {got.get('flags')!r} != {want['flags']!r}")
        for col in ("reported_links", "fan_in_24h"):
            if int(got[col]) != want[col]:
                problems.append(f"payee {key}.{col}: view {got[col]!r} != {want[col]!r}")
        if str(got["is_merchant"]).lower() != str(want["is_merchant"]).lower():
            problems.append(
                f"payee {key}.is_merchant: view {got['is_merchant']!r} != {want['is_merchant']!r}"
            )

    if problems:
        print(f"\nMISMATCH ({len(problems)}):")
        for p in problems[:25]:
            print("  " + p)
        sys.exit(1)
    print(f"\nOK: {len(payers):,} payers and {len(payees):,} payees match features.json exactly.")


if __name__ == "__main__":
    main()

"""Small helper tables that only BigQuery needs (Parquet only, loaded by data/bq/load.sh).

meta                   one row: the dataset's AS_OF and windows, so the feature views compute
                       "as of" the synthetic world's clock instead of CURRENT_TIMESTAMP()
demo_payer_features    the pinned demo rows from pinned_features.json, unioned into the views
demo_payee_features    so the demo fixtures behave the same with TRUSTSHIELD_FEATURE_STORE=bigquery
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import config as C
from .features import load_pinned

META_SCHEMA = pa.schema(
    [
        ("as_of", pa.timestamp("us", tz="UTC")),
        ("window_days", pa.int64()),
        ("recent_vpa_days", pa.int64()),
        ("seed", pa.int64()),
    ]
)
DEMO_PAYER_SCHEMA = pa.schema(
    [
        ("payer_id", pa.string()),
        ("median_amount", pa.float64()),
        ("avg_daily_txn", pa.float64()),
        ("txn_count_1h", pa.int64()),
        ("txn_count_24h", pa.int64()),
    ]
)
DEMO_PAYEE_SCHEMA = pa.schema(
    [
        ("payee_vpa", pa.string()),
        ("flags", pa.list_(pa.string())),
        ("reported_links", pa.int64()),
        ("fan_in_24h", pa.int64()),
        ("is_merchant", pa.bool_()),
    ]
)


def bq_tables(seed: int) -> dict[str, pa.Table]:
    pinned = load_pinned()
    meta = pa.Table.from_pylist(
        [
            {
                "as_of": pd.Timestamp(C.AS_OF).tz_convert("UTC").to_pydatetime(),
                "window_days": C.WINDOW_DAYS,
                "recent_vpa_days": C.RECENT_VPA_DAYS,
                "seed": seed,
            }
        ],
        schema=META_SCHEMA,
    )
    payers = pa.Table.from_pylist(
        [
            {
                "payer_id": key,
                "median_amount": None
                if row["median_amount"] is None
                else float(row["median_amount"]),
                "avg_daily_txn": float(row["avg_daily_txn"]),
                "txn_count_1h": int(row["txn_count_1h"]),
                "txn_count_24h": int(row["txn_count_24h"]),
            }
            for key, row in pinned["payers"].items()
        ],
        schema=DEMO_PAYER_SCHEMA,
    )
    payees = pa.Table.from_pylist(
        [{"payee_vpa": key.lower(), **row} for key, row in pinned["payees"].items()],
        schema=DEMO_PAYEE_SCHEMA,
    )
    return {"meta": meta, "demo_payer_features": payers, "demo_payee_features": payees}


def write_bq_tables(seed: int, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, table in bq_tables(seed).items():
        pq.write_table(table, out_dir / f"{name}.parquet")
        counts[name] = table.num_rows
    return counts

"""Write the dataset to data/out/ (Parquet + CSV) and features.json for the agents."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from .bq_tables import write_bq_tables
from .features import build_features, dumps
from .payguard import build_payguard_mocks, dumps_ledger, dumps_screenshots
from .pipeline import TABLES, Dataset

DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = DATA_DIR / "out"
DEFAULT_FEATURES = DATA_DIR.parent / "services" / "agents" / "data" / "mock" / "features.json"


def write_tables(ds: Dataset, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in TABLES:
        df = ds[name]
        table = pa.Table.from_pandas(df, preserve_index=False)
        # pandas 3 strings are Arrow large_string; plain string is the safest type for bq load.
        table = table.cast(
            pa.schema(
                [
                    f.with_type(pa.string()) if pa.types.is_large_string(f.type) else f
                    for f in table.schema
                ],
                metadata=table.schema.metadata,
            )
        )
        pq.write_table(table, out_dir / f"{name}.parquet")
        df.to_csv(out_dir / f"{name}.csv", index=False, lineterminator="\n")
        counts[name] = len(df)
    counts.update(write_bq_tables(ds.seed, out_dir))  # Parquet only: meta + pinned demo rows
    manifest = {"seed": ds.seed, "row_counts": counts}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return counts


def write_payguard_mocks(ds: Dataset, mock_dir: Path) -> tuple[dict, dict]:
    """merchant_ledger.json + screenshots.json next to features.json."""
    ledger, shots = build_payguard_mocks(ds)
    mock_dir.mkdir(parents=True, exist_ok=True)
    (mock_dir / "merchant_ledger.json").write_text(
        dumps_ledger(ledger), encoding="utf-8", newline="\n"
    )
    (mock_dir / "screenshots.json").write_text(
        dumps_screenshots(shots), encoding="utf-8", newline="\n"
    )
    return ledger, shots


def write_features(ds: Dataset, path: Path) -> dict:
    features = build_features(ds)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(features), encoding="utf-8", newline="\n")
    return features

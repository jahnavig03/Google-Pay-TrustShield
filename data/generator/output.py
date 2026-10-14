"""Write the dataset to data/out/ (Parquet + CSV) and features.json for the agents."""

from __future__ import annotations

import json
from pathlib import Path

from .features import build_features, dumps
from .pipeline import TABLES, Dataset

DATA_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT = DATA_DIR / "out"
DEFAULT_FEATURES = DATA_DIR.parent / "services" / "agents" / "data" / "mock" / "features.json"


def write_tables(ds: Dataset, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name in TABLES:
        df = ds[name]
        df.to_parquet(out_dir / f"{name}.parquet", index=False, engine="pyarrow")
        df.to_csv(out_dir / f"{name}.csv", index=False, lineterminator="\n")
        counts[name] = len(df)
    manifest = {"seed": ds.seed, "row_counts": counts}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return counts


def write_features(ds: Dataset, path: Path) -> dict:
    features = build_features(ds)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(features), encoding="utf-8", newline="\n")
    return features

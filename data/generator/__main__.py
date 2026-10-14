"""python -m generator --seed 42 [--out data/out] [--features PATH | --no-features]"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from .output import DEFAULT_FEATURES, DEFAULT_OUT, write_features, write_tables
from .pipeline import generate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="generator", description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Parquet + CSV folder")
    parser.add_argument(
        "--features", type=Path, default=DEFAULT_FEATURES, help="where to write features.json"
    )
    parser.add_argument(
        "--no-features", action="store_true", help="don't touch the agents' features.json"
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    ds = generate(args.seed)
    counts = write_tables(ds, args.out)
    for name, n in counts.items():
        print(f"{name:<16} {n:>7,} rows")
    if not args.no_features:
        features = write_features(ds, args.features)
        print(
            f"features.json    {len(features['payers']):,} payers, "
            f"{len(features['payees']):,} payees -> {args.features}"
        )
    print(f"seed {args.seed} -> {args.out} in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()

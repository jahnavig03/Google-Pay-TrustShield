"""`python -m generator --seed 42` must produce byte-identical files every time."""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1]


def _run(out: Path, hash_seed: str, seed: int = 42) -> dict[str, str]:
    env = {**os.environ, "PYTHONHASHSEED": hash_seed}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "generator",
            "--seed",
            str(seed),
            "--out",
            str(out),
            "--features",
            str(out / "features.json"),
        ],
        cwd=DATA_DIR,
        env=env,
        check=True,
        capture_output=True,
    )
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir())}


def test_same_seed_gives_identical_files(tmp_path):
    # Different hash seeds: catches any dependence on set / dict-of-str iteration order.
    first = _run(tmp_path / "a", "1")
    second = _run(tmp_path / "b", "12345")
    assert first == second
    assert {"transactions.parquet", "transactions.csv", "features.json"} <= set(first)


def test_different_seed_gives_different_data(tmp_path):
    a = _run(tmp_path / "a", "1", seed=42)
    b = _run(tmp_path / "b", "1", seed=7)
    assert a["transactions.csv"] != b["transactions.csv"]

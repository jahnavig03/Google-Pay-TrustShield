"""data/bq/: the DDL matches the Parquet files bq load reads, and the SQL is project-agnostic.

These run offline. The live check (views == features.json) is data/bq/verify.py.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from generator.output import write_tables

BQ = Path(__file__).resolve().parents[1] / "bq"
SCHEMA_FILES = sorted((BQ / "schema").glob("*.sql"))
VIEW_FILES = sorted((BQ / "views").glob("*.sql"))


def _arrow_to_bq(t: pa.DataType) -> str:
    if pa.types.is_string(t) or pa.types.is_large_string(t):
        return "STRING"
    if pa.types.is_int64(t):
        return "INT64"
    if pa.types.is_float64(t):
        return "FLOAT64"
    if pa.types.is_boolean(t):
        return "BOOL"
    if pa.types.is_timestamp(t):
        assert t.unit == "us" and str(t.tz) == "UTC", t  # BigQuery TIMESTAMP is UTC microseconds
        return "TIMESTAMP"
    if pa.types.is_list(t):
        return f"ARRAY<{_arrow_to_bq(t.value_type)}>"
    raise AssertionError(f"no BigQuery type for {t}")


def _ddl_columns(path: Path) -> dict[str, str]:
    body = path.read_text(encoding="utf-8").split("(", 1)[1]
    return dict(re.findall(r"^\s+(\w+)\s+([A-Z0-9_]+(?:<[A-Z0-9_]+>)?)", body, re.MULTILINE))


def _load_sh_tables() -> list[str]:
    text = (BQ / "load.sh").read_text(encoding="utf-8")
    block = re.search(r"TABLES=\(([^)]*)\)", text).group(1)
    return block.split()


@pytest.fixture(scope="module")
def out_dir(ds, tmp_path_factory):
    out = tmp_path_factory.mktemp("out")
    write_tables(ds, out)
    return out


def test_every_loaded_table_has_ddl_and_a_parquet_file(out_dir):
    tables = _load_sh_tables()
    assert sorted(tables) == sorted(p.stem for p in SCHEMA_FILES)
    for name in tables:
        assert (out_dir / f"{name}.parquet").exists(), name
    # The five tables the spec asks for.
    assert {"transactions", "beneficiaries", "devices", "labels", "merchant_ledger"} <= set(tables)


@pytest.mark.parametrize("ddl", SCHEMA_FILES, ids=lambda p: p.stem)
def test_ddl_matches_the_parquet_schema(ddl, out_dir):
    parquet = pq.read_schema(out_dir / f"{ddl.stem}.parquet")
    actual = {f.name: _arrow_to_bq(f.type) for f in parquet}
    assert _ddl_columns(ddl) == actual


def test_sql_never_hard_codes_a_project_or_dataset():
    for path in SCHEMA_FILES + VIEW_FILES:
        sql = path.read_text(encoding="utf-8")
        refs = re.findall(r"`([^`]+)`", sql)
        assert refs, path
        for ref in refs:
            assert ref.startswith("{{project}}.{{dataset}}."), (path.name, ref)
        assert "qualified-sun" not in sql


def test_views_only_read_tables_we_create():
    created = {p.stem for p in SCHEMA_FILES}
    for path in VIEW_FILES:
        sql = path.read_text(encoding="utf-8")
        own = re.search(r"VIEW `\{\{project\}\}\.\{\{dataset\}\}\.(\w+)`", sql).group(1)
        assert own == path.stem
        read = set(re.findall(r"`\{\{project\}\}\.\{\{dataset\}\}\.(\w+)`", sql)) - {own}
        assert read <= created, read - created


def test_view_columns_match_features_json():
    """The pinned demo tables share the views' output columns, in features.json order."""
    assert list(_ddl_columns(BQ / "schema" / "demo_payer_features.sql")) == [
        "payer_id", "median_amount", "avg_daily_txn", "txn_count_1h", "txn_count_24h",
    ]  # fmt: skip
    assert _ddl_columns(BQ / "schema" / "demo_payee_features.sql") == {
        "payee_vpa": "STRING",
        "flags": "ARRAY<STRING>",
        "reported_links": "INT64",
        "fan_in_24h": "INT64",
        "is_merchant": "BOOL",
    }


def test_load_script_never_streams():
    text = (BQ / "load.sh").read_text(encoding="utf-8")
    assert "bq insert" not in text and "insertAll" not in text and "tabledata" not in text
    assert "--dry_run" in text


def _working_bash() -> bool:
    # On Windows `bash` can be an unconfigured WSL stub; only use a bash that actually runs.
    if shutil.which("bash") is None:
        return False
    return subprocess.run(["bash", "-c", "true"], capture_output=True, check=False).returncode == 0


@pytest.mark.skipif(not _working_bash(), reason="no working bash on PATH")
def test_load_script_parses():
    subprocess.run(["bash", "-n", (BQ / "load.sh").as_posix()], check=True)

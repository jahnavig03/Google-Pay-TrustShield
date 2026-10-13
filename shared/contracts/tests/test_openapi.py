import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_committed_openapi_matches_models():
    pytest.importorskip("fastapi")
    build_app = runpy.run_path(str(ROOT / "scripts" / "export_openapi.py"))["build_app"]
    committed = json.loads((ROOT / "openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(build_app().openapi())), (
        "openapi.json is stale: run python scripts/export_openapi.py"
    )

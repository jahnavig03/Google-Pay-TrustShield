"""Load the demo-story fixtures in shared/contracts/fixtures/."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

DEMO1_PAYMENT = "demo1_payment_85k"
DEMO2_CASE = "demo2_analyst_case"
DEMO3_SCREENSHOT = "demo3_fake_screenshot_12k"


def fixtures_dir() -> Path:
    override = os.environ.get("TRUSTSHIELD_FIXTURES_DIR")
    if override:
        return Path(override)
    # src/trustshield_contracts/fixtures.py -> shared/contracts/fixtures
    return Path(__file__).resolve().parents[2] / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((fixtures_dir() / f"{name}.json").read_text(encoding="utf-8"))

"""PayeeDirectory backed by data/mock/payee_directory.json (synthetic registered names).

gcp mode uses it too until the BigQuery accounts table is exposed as a directory view.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..paths import mock_data_dir


class JsonPayeeDirectory:
    def __init__(self, path: Path | None = None):
        data = json.loads(
            (path or mock_data_dir() / "payee_directory.json").read_text(encoding="utf-8")
        )
        self._names = {vpa.lower(): name for vpa, name in data.get("registered_names", {}).items()}

    async def registered_name(self, payee_vpa: str) -> str | None:
        return self._names.get(payee_vpa.lower())

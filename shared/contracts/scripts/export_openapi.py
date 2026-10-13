"""Export shared/contracts/openapi.json from the contract models.

Builds a throwaway FastAPI app with stub routes from trustshield_contracts.api.ENDPOINTS,
so the output has real paths and component schemas for openapi-typescript.

    pip install -e ".[openapi]"
    python scripts/export_openapi.py
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from fastapi import FastAPI

from trustshield_contracts import __version__
from trustshield_contracts.api import ENDPOINTS, Endpoint

OUT = Path(__file__).resolve().parents[1] / "openapi.json"


def _stub(endpoint: Endpoint):
    """A handler whose signature declares the path params and request body for FastAPI."""
    params = [
        inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
        for name in re.findall(r"{(\w+)}", endpoint.path)
    ]
    if endpoint.request_model is not None:
        params.append(
            inspect.Parameter(
                "body", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=endpoint.request_model
            )
        )

    def handler(**_kwargs):
        raise NotImplementedError

    handler.__signature__ = inspect.Signature(params)
    return handler


def build_app() -> FastAPI:
    app = FastAPI(
        title="TrustShield API",
        version=__version__,
        description="Prototype simulator — synthetic data. Not affiliated with Google Pay.",
    )
    for ep in ENDPOINTS:
        app.add_api_route(
            ep.path,
            _stub(ep),
            methods=[ep.method],
            response_model=ep.response_model,
            operation_id=ep.operation_id,
            summary=ep.summary,
            tags=[ep.tag],
        )
    return app


def main() -> None:
    spec = build_app().openapi()
    OUT.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(spec['paths'])} paths, {len(spec['components']['schemas'])} schemas)")


if __name__ == "__main__":
    main()

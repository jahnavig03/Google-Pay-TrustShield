"""Every route in the frozen contract registry must exist here, with the same shapes.

The check runs against the generated OpenAPI document, which is what web/ consumes.
"""

from __future__ import annotations

import pytest
from trustshield_contracts.api import ENDPOINTS

from trustshield_gateway.app import create_app

SCHEMA = create_app().openapi()
PATHS = SCHEMA["paths"]


def _schema_name(model: type) -> str:
    return model.__name__


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e.operation_id)
def test_endpoint_is_implemented(endpoint):
    operations = PATHS.get(endpoint.path)
    assert operations is not None, f"{endpoint.path} is missing"
    operation = operations.get(endpoint.method.lower())
    assert operation is not None, f"{endpoint.method} {endpoint.path} is missing"
    assert operation["operationId"] == endpoint.operation_id
    assert endpoint.tag in operation["tags"]

    response_ref = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert response_ref.endswith(f"/{_schema_name(endpoint.response_model)}")

    if endpoint.request_model is None:
        assert "requestBody" not in operation
    else:
        request_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
        assert request_ref.endswith(f"/{_schema_name(endpoint.request_model)}")


def test_health_endpoint_exists():
    assert "get" in PATHS["/health"]


def test_no_undeclared_api_routes():
    declared = {(e.path, e.method.lower()) for e in ENDPOINTS}
    implemented = {
        (path, method)
        for path, operations in PATHS.items()
        if path.startswith("/api/v1")
        for method in operations
    }
    assert implemented == declared

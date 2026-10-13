import pytest
from trustshield_contracts import PaymentRiskRequest
from trustshield_contracts.fixtures import DEMO1_PAYMENT, load_fixture

from trustshield_agents.risk import load_risk_config


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("TRUSTSHIELD_MODE", "mock")
    monkeypatch.delenv("TRUSTSHIELD_ORG_ID", raising=False)
    monkeypatch.delenv("TRUSTSHIELD_RISK_CONFIG", raising=False)
    monkeypatch.delenv("TRUSTSHIELD_FEATURE_STORE", raising=False)


@pytest.fixture
def cfg():
    return load_risk_config()


@pytest.fixture
def demo1_request() -> PaymentRiskRequest:
    return PaymentRiskRequest.model_validate(load_fixture(DEMO1_PAYMENT)["request"])

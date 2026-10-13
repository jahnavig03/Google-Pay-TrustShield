from trustshield_contracts import Decision

from trustshield_agents.adapters.static_evidence import StaticEvidenceProvider


def test_every_mapped_id_is_in_catalog():
    ev = StaticEvidenceProvider()
    for risk_type in ev._by_risk_type:
        for decision in Decision:
            ids = ev.evidence_ids(risk_type, decision)
            assert ids
            assert len(ev.citations(ids)) == len(ids)


def test_unknown_risk_type_falls_back():
    assert StaticEvidenceProvider().evidence_ids("something_new", Decision.WARN)

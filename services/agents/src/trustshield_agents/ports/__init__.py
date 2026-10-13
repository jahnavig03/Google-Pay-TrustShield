"""Interfaces for every external dependency. Adapters in ../adapters implement them."""

from .evidence import EvidenceProvider
from .feature_store import FeatureStore, PayeeFeatures, PayerFeatures
from .message_writer import CustomerMessageWriter, MessageInputs
from .scam_classifier import ScamAssessment, ScamClassifier, ScamPattern

__all__ = [
    "CustomerMessageWriter",
    "EvidenceProvider",
    "FeatureStore",
    "MessageInputs",
    "PayeeFeatures",
    "PayerFeatures",
    "ScamAssessment",
    "ScamClassifier",
    "ScamPattern",
]

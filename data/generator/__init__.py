"""Seeded synthetic data generator for TrustShield. SYNTHETIC data only.

python -m generator --seed 42
"""

from .pipeline import Dataset, generate

__all__ = ["Dataset", "generate"]

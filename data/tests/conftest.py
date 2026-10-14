import pytest

from generator import generate


@pytest.fixture(scope="session")
def ds():
    """The seed-42 dataset, generated once per test session (~10 s)."""
    return generate(42)

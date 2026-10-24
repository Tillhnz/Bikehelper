import pytest


@pytest.fixture(autouse=True)
def _reset_ratelimit():
    """Alle Tests melden sich von derselben Adresse an; die Drosselung soll sie nicht gegenseitig stören."""
    from app import ratelimit
    ratelimit.reset()
    yield
    ratelimit.reset()

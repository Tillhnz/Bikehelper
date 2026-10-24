import os

# Die Tests legen viele Konten an; die offene Registrierung ist im Betrieb standardmäßig aus
os.environ.setdefault("ALLOW_REGISTRATION", "true")

import pytest


@pytest.fixture(autouse=True)
def _reset_ratelimit():
    """Alle Tests melden sich von derselben Adresse an; die Drosselung soll sie nicht gegenseitig stören."""
    from app import ratelimit
    ratelimit.reset()
    yield
    ratelimit.reset()

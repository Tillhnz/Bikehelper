import pytest
from fastapi import HTTPException

from app import ratelimit


def setup_function(_):
    ratelimit.reset()


def test_login_is_blocked_after_too_many_failures_and_recovers():
    for i in range(ratelimit.LIMIT_PER_EMAIL):
        ratelimit.check_login("a@example.com", "1.1.1.1", now=100 + i)
        ratelimit.record_failure("a@example.com", "1.1.1.1", now=100 + i)
    with pytest.raises(HTTPException) as e:
        ratelimit.check_login("a@example.com", "2.2.2.2", now=200)  # andere Adresse, gleiche E-Mail
    assert e.value.status_code == 429 and int(e.value.headers["Retry-After"]) > 0
    ratelimit.check_login("b@example.com", "3.3.3.3", now=200)  # andere E-Mail bleibt frei
    ratelimit.check_login("a@example.com", "2.2.2.2", now=100 + ratelimit.WINDOW_S + 10)  # nach dem Fenster wieder frei


def test_success_clears_the_email_counter():
    for i in range(ratelimit.LIMIT_PER_EMAIL - 1):
        ratelimit.record_failure("c@example.com", "4.4.4.4", now=10 + i)
    ratelimit.record_success("c@example.com")
    ratelimit.record_failure("c@example.com", "4.4.4.4", now=50)
    ratelimit.check_login("c@example.com", "4.4.4.4", now=51)


def test_register_is_limited_per_address():
    for i in range(ratelimit.LIMIT_REGISTER_PER_IP):
        ratelimit.check_register("5.5.5.5", now=i)
    with pytest.raises(HTTPException):
        ratelimit.check_register("5.5.5.5", now=100)

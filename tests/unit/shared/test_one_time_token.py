from datetime import datetime, timedelta, timezone

from app.shared.security.one_time_token import OneTimeTokenService


def test_generate_returns_token_and_its_sha256():
    service = OneTimeTokenService()

    token, token_hash = service.generate()

    assert len(token_hash) == 64
    assert token not in token_hash
    assert service.hash(token) == token_hash


def test_tokens_are_unique():
    service = OneTimeTokenService()
    assert service.generate()[0] != service.generate()[0]


def test_expiry_accepts_naive_datetimes():
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

    assert OneTimeTokenService.is_expired(datetime(2026, 10, 28, 11, 59), now)
    assert not OneTimeTokenService.is_expired(datetime(2026, 10, 28, 12, 1), now)


def test_expires_at_adds_ttl():
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)

    assert OneTimeTokenService.expires_at(timedelta(hours=48), now) == now + timedelta(
        hours=48
    )

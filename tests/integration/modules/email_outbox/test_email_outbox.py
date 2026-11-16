from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.errors import EmailSendError
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer, UnknownTemplateError
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.service import (
    EmailOutbox,
    EmailOutboxWorker,
    RetryPolicy,
)
from app.modules.users.model import User  # noqa: F401  (FK de created_by)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CONTEXT = {
    "user_name": "Fulana",
    "invite_link": "https://exemplo.com/convite/TOKEN-SECRETO",
    "expires_at": "2026-10-30T12:00:00+00:00",
    "invited_by": "Admin",
}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _transient() -> EmailSendError:
    return EmailSendError("timeout", transient=True, failover=True, provider="smtp")


def _permanent() -> EmailSendError:
    return EmailSendError(
        "550 5.1.1 user unknown",
        transient=False,
        failover=False,
        provider="smtp",
        smtp_code=550,
    )


@pytest.fixture
def outbox(db):
    return EmailOutbox(EmailOutboxRepository(db))


@pytest.fixture
def clock():
    return Clock(NOW + timedelta(seconds=1))


def make_worker(db, provider, clock) -> EmailOutboxWorker:
    return EmailOutboxWorker(
        EmailOutboxRepository(db),
        EmailRenderer(StaticBrandingProvider()),
        provider,
        get_settings(),
        clock=clock,
        worker_id="w1",
    )


def enqueue(db, outbox, **kwargs) -> EmailOutboxItem:
    item = outbox.enqueue("user_invite", dict(CONTEXT), "fulana@test.com", **kwargs)
    item.next_attempt_at = NOW
    db.commit()
    return item


class TestEnqueue:
    def test_repeated_idempotency_key_does_not_duplicate(self, db, outbox):
        first = enqueue(db, outbox, idempotency_key="invite:1")
        second = enqueue(db, outbox, idempotency_key="invite:1")

        assert first.id == second.id
        assert db.query(EmailOutboxItem).count() == 1

    def test_unknown_template_is_refused(self, outbox):
        with pytest.raises(UnknownTemplateError):
            outbox.enqueue("nao_existe", {}, "x@test.com")

    def test_rollback_discards_email(self, db, outbox):
        outbox.enqueue("user_invite", dict(CONTEXT), "fulana@test.com")
        db.rollback()

        assert db.query(EmailOutboxItem).count() == 0


class TestWorker:
    def test_sends_and_records_result(self, db, outbox, clock):
        item = enqueue(db, outbox)
        email = FakeEmailService()

        assert make_worker(db, email, clock).run_once() == 1

        db.refresh(item)
        assert item.status == EmailStatus.SENT
        assert item.attempts == 1
        assert item.provider == "fake"
        assert item.provider_message_id
        assert email.messages[0].headers["X-Email-Id"] == item.id

    def test_sent_item_is_not_sent_again(self, db, outbox, clock):
        enqueue(db, outbox)
        email = FakeEmailService()
        worker = make_worker(db, email, clock)

        worker.run_once()
        worker.run_once()

        assert len(email.messages) == 1

    def test_token_is_masked_after_sending(self, db, outbox, clock):
        item = enqueue(db, outbox)

        make_worker(db, FakeEmailService(), clock).run_once()

        db.refresh(item)
        assert "TOKEN-SECRETO" not in item.html
        assert "TOKEN-SECRETO" not in item.text
        assert "TOKEN-SECRETO" not in str(item.context)
        assert item.context["user_name"] == "Fulana"

    def test_transient_failure_is_retried_later(self, db, outbox, clock):
        item = enqueue(db, outbox)

        assert make_worker(db, FakeEmailService(_transient()), clock).run_once() == 0

        db.refresh(item)
        assert item.status == EmailStatus.FAILED
        assert "timeout" in item.last_error
        assert item.next_attempt_at.replace(tzinfo=timezone.utc) > clock.now

    def test_failed_item_waits_for_next_attempt(self, db, outbox, clock):
        enqueue(db, outbox)
        make_worker(db, FakeEmailService(_transient()), clock).run_once()
        email = FakeEmailService()

        make_worker(db, email, clock).run_once()
        assert email.messages == []

        clock.now += timedelta(hours=1)
        make_worker(db, email, clock).run_once()
        assert len(email.messages) == 1

    def test_permanent_failure_goes_dead(self, db, outbox, clock):
        item = enqueue(db, outbox)

        make_worker(db, FakeEmailService(_permanent()), clock).run_once()

        db.refresh(item)
        assert item.status == EmailStatus.DEAD
        assert item.attempts == 1
        assert "TOKEN-SECRETO" not in str(item.context)

    def test_goes_dead_after_max_attempts(self, db, outbox, clock):
        item = enqueue(db, outbox)
        worker = make_worker(db, FakeEmailService(_transient()), clock)

        for _ in range(get_settings().email_max_attempts):
            worker.run_once()
            clock.now += timedelta(days=1)

        db.refresh(item)
        assert item.status == EmailStatus.DEAD
        assert item.attempts == get_settings().email_max_attempts

    def test_stuck_sending_item_is_recovered(self, db, outbox, clock):
        item = enqueue(db, outbox)
        item.status = EmailStatus.SENDING
        item.locked_at = NOW - timedelta(minutes=30)
        item.locked_by = "worker-que-caiu"
        db.commit()
        email = FakeEmailService()

        make_worker(db, email, clock).run_once()

        db.refresh(item)
        assert item.status == EmailStatus.SENT
        assert len(email.messages) == 1

    def test_recent_sending_item_is_left_alone(self, db, outbox, clock):
        item = enqueue(db, outbox)
        item.status = EmailStatus.SENDING
        item.locked_at = clock.now - timedelta(minutes=1)
        db.commit()
        email = FakeEmailService()

        make_worker(db, email, clock).run_once()

        assert email.messages == []

    def test_cancelled_item_is_not_sent(self, db, outbox, clock):
        enqueue(db, outbox, idempotency_key="invite:9")
        assert outbox.cancel_pending("invite:9")
        db.commit()
        email = FakeEmailService()

        make_worker(db, email, clock).run_once()

        assert email.messages == []


class TestRetryPolicy:
    def test_delay_grows_and_respects_ceiling(self):
        policy = RetryPolicy(base_seconds=60, max_seconds=600, max_attempts=6)

        delays = [policy.delay(n, jitter=1.0).total_seconds() for n in range(1, 6)]

        assert delays == [60, 120, 240, 480, 600]

    def test_jitter_stays_within_20_percent(self):
        policy = RetryPolicy(base_seconds=100, max_seconds=1000, max_attempts=6)

        for _ in range(50):
            assert 80 <= policy.delay(1).total_seconds() <= 120

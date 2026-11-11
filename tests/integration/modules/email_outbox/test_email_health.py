from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.errors import EmailSendError
from app.modules.email.failover import FailoverEmailService
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email_outbox.alerts import ALERT_TEMPLATE, EmailAlerts
from app.modules.email_outbox.model import (
    BreakerState,
    EmailAttempt,
    EmailOutboxItem,
    EmailProviderHealth,
    EmailStatus,
)
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.service import EmailOutbox, EmailOutboxWorker
from app.modules.users.repository import UserRepository
from app.shared.types import Role

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
CONTEXT = {"sent_at": "2026-10-28T09:00:00-03:00"}


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class NamedFake(FakeEmailService):
    def __init__(self, name: str, fail_with: EmailSendError | None = None) -> None:
        super().__init__(fail_with)
        self.name = name


def provider_down(name: str) -> EmailSendError:
    return EmailSendError(
        "connection refused", transient=True, failover=True, provider=name
    )


@pytest.fixture
def clock():
    return Clock(NOW)


@pytest.fixture
def outbox(db):
    return EmailOutbox(EmailOutboxRepository(db))


@pytest.fixture
def admin(db):
    user = UserRepository(db).create(
        name="Admin", email="admin@test.com", hashed_password="x", role=Role.ADMIN
    )
    db.commit()
    return user


def settings_with(**overrides):
    return get_settings().model_copy(update=overrides)


def make_worker(db, provider, clock, alerts=None, **overrides):
    return EmailOutboxWorker(
        EmailOutboxRepository(db),
        EmailRenderer(StaticBrandingProvider()),
        provider,
        settings_with(**overrides),
        clock=clock,
        worker_id="w1",
        alerts=alerts,
    )


def enqueue(db, outbox, count=1):
    for _ in range(count):
        item = outbox.enqueue("test", dict(CONTEXT), "dest@test.com")
        item.next_attempt_at = NOW - timedelta(seconds=1)
        item.created_at = NOW - timedelta(seconds=1)
    db.commit()


def health(db, provider) -> EmailProviderHealth | None:
    return db.get(EmailProviderHealth, provider)


class TestCircuitBreaker:
    def test_five_failures_open_the_circuit(self, db, outbox, clock):
        enqueue(db, outbox, 5)
        smtp = NamedFake("smtp", provider_down("smtp"))

        make_worker(db, smtp, clock, email_rate_limit_per_minute=0).run_once()

        state = health(db, "smtp")
        assert state.state == BreakerState.OPEN
        assert state.consecutive_failures == 5

    def test_open_circuit_goes_straight_to_backup(self, db, outbox, clock):
        db.add(
            EmailProviderHealth(
                provider="smtp",
                state=BreakerState.OPEN,
                consecutive_failures=5,
                opened_at=NOW,
            )
        )
        enqueue(db, outbox)
        smtp = NamedFake("smtp")
        backup = NamedFake("resend")

        make_worker(db, FailoverEmailService([smtp, backup]), clock).run_once()

        assert smtp.messages == []
        assert len(backup.messages) == 1

    def test_after_cooldown_one_success_closes(self, db, outbox, clock):
        db.add(
            EmailProviderHealth(
                provider="smtp",
                state=BreakerState.OPEN,
                consecutive_failures=5,
                opened_at=NOW - timedelta(minutes=10),
            )
        )
        enqueue(db, outbox)
        smtp = NamedFake("smtp")

        make_worker(db, smtp, clock).run_once()

        assert len(smtp.messages) == 1
        assert health(db, "smtp").state == BreakerState.CLOSED
        assert health(db, "smtp").consecutive_failures == 0

    def test_half_open_failure_opens_again(self, db, outbox, clock):
        db.add(
            EmailProviderHealth(
                provider="smtp",
                state=BreakerState.OPEN,
                consecutive_failures=5,
                opened_at=NOW - timedelta(minutes=10),
            )
        )
        enqueue(db, outbox)

        make_worker(db, NamedFake("smtp", provider_down("smtp")), clock).run_once()

        state = health(db, "smtp")
        assert state.state == BreakerState.OPEN
        assert state.opened_at.replace(tzinfo=timezone.utc) == NOW

    def test_recipient_error_does_not_count(self, db, outbox, clock):
        enqueue(db, outbox, 6)
        rejected = EmailSendError(
            "550 user unknown",
            transient=False,
            failover=False,
            provider="smtp",
            smtp_code=550,
        )

        make_worker(db, NamedFake("smtp", rejected), clock).run_once()

        state = health(db, "smtp")
        assert state is None or state.state == BreakerState.CLOSED


class TestRateLimitAndTimeline:
    def test_rate_limit_holds_the_batch(self, db, outbox, clock):
        enqueue(db, outbox, 5)
        email = FakeEmailService()

        sent = make_worker(db, email, clock, email_rate_limit_per_minute=3).run_once()

        assert sent == 3
        assert (
            db.query(EmailOutboxItem).filter_by(status=EmailStatus.PENDING).count() == 2
        )

    def test_rate_limit_counts_last_minute(self, db, outbox, clock):
        enqueue(db, outbox, 4)
        worker = make_worker(
            db, FakeEmailService(), clock, email_rate_limit_per_minute=2
        )

        assert worker.run_once() == 2
        assert worker.run_once() == 0
        clock.now += timedelta(seconds=61)
        assert worker.run_once() == 2

    def test_each_attempt_is_recorded(self, db, outbox, clock):
        enqueue(db, outbox)
        make_worker(db, NamedFake("smtp", provider_down("smtp")), clock).run_once()
        clock.now += timedelta(hours=1)
        make_worker(db, NamedFake("smtp"), clock).run_once()

        attempts = db.query(EmailAttempt).order_by(EmailAttempt.attempt).all()
        assert [a.success for a in attempts] == [False, True]
        assert attempts[0].error == "connection refused"
        assert attempts[1].provider == "smtp"


class TestAlerts:
    def alerts(self, db, outbox, **overrides):
        return EmailAlerts(outbox, UserRepository(db), settings_with(**overrides))

    def alert_items(self, db):
        return db.query(EmailOutboxItem).filter_by(template_id=ALERT_TEMPLATE).all()

    def test_dead_email_alerts_admins_once_per_interval(self, db, outbox, clock, admin):
        enqueue(db, outbox, 2)
        rejected = EmailSendError(
            "550", transient=False, failover=False, provider="smtp"
        )
        alerts = self.alerts(db, outbox)

        make_worker(db, FakeEmailService(rejected), clock, alerts=alerts).run_once()
        enqueue(db, outbox)
        make_worker(db, FakeEmailService(rejected), clock, alerts=alerts).run_once()

        items = self.alert_items(db)
        assert len(items) == 1
        assert items[0].to == [admin.email]
        assert "não entregue" in items[0].context["title"]

    def test_alert_comes_back_after_interval(self, db, outbox, clock, admin):
        rejected = EmailSendError(
            "550", transient=False, failover=False, provider="smtp"
        )
        alerts = self.alerts(db, outbox, email_alert_throttle_minutes=60)
        enqueue(db, outbox)
        make_worker(db, FakeEmailService(rejected), clock, alerts=alerts).run_once()

        clock.now += timedelta(minutes=61)
        enqueue(db, outbox)
        for item in db.query(EmailOutboxItem).filter_by(status=EmailStatus.PENDING):
            if item.template_id != ALERT_TEMPLATE:
                item.next_attempt_at = clock.now - timedelta(seconds=1)
        db.commit()
        make_worker(db, FakeEmailService(rejected), clock, alerts=alerts).run_once()

        assert len(self.alert_items(db)) == 2

    def test_dead_alert_email_does_not_alert_again(self, db, outbox, clock, admin):
        rejected = EmailSendError(
            "550", transient=False, failover=False, provider="smtp"
        )
        item = outbox.enqueue(
            ALERT_TEMPLATE,
            {"title": "x", "detail": "y", "occurred_at": NOW.isoformat()},
            admin.email,
        )
        item.next_attempt_at = NOW - timedelta(seconds=1)
        db.commit()

        make_worker(
            db, FakeEmailService(rejected), clock, alerts=self.alerts(db, outbox)
        ).run_once()

        assert len(self.alert_items(db)) == 1

    def test_circuit_open_alerts(self, db, outbox, clock, admin):
        enqueue(db, outbox, 5)

        make_worker(
            db,
            NamedFake("smtp", provider_down("smtp")),
            clock,
            alerts=self.alerts(db, outbox),
        ).run_once()

        titles = [i.context["title"] for i in self.alert_items(db)]
        assert "Provedor de e-mail pausado: smtp" in titles

    def test_backlog_alerts(self, db, outbox, clock, admin):
        enqueue(db, outbox, 3)
        for item in db.query(EmailOutboxItem):
            item.created_at = NOW - timedelta(minutes=30)
            item.next_attempt_at = NOW + timedelta(hours=1)
        db.commit()

        make_worker(
            db,
            FakeEmailService(),
            clock,
            alerts=self.alerts(
                db, outbox, email_backlog_alert_size=3, email_backlog_alert_minutes=15
            ),
        ).run_once()

        titles = [i.context["title"] for i in self.alert_items(db)]
        assert "Fila de e-mails acumulada" in titles


class TestRetention:
    def test_old_bodies_are_purged_and_metadata_kept(self, db, outbox, clock):
        enqueue(db, outbox)
        worker = make_worker(db, FakeEmailService(), clock)
        worker.run_once()
        item = db.query(EmailOutboxItem).one()
        item.created_at = NOW - timedelta(days=200)
        db.commit()

        assert worker.purge_old_bodies(timedelta(days=180)) == 1

        db.refresh(item)
        assert item.html is None
        assert item.context == {}
        assert item.status == EmailStatus.SENT
        assert item.to == ["dest@test.com"]

    def test_recent_and_pending_are_kept(self, db, outbox, clock):
        enqueue(db, outbox)
        worker = make_worker(db, FakeEmailService(), clock)

        assert worker.purge_old_bodies(timedelta(days=180)) == 0

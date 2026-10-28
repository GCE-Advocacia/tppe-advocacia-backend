from datetime import date, datetime, timedelta, timezone

import pytest

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.errors import EmailSendError
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email_outbox.logs_service import EmailLogService
from app.modules.email_outbox.model import (
    BreakerState,
    EmailProviderHealth,
    EmailStatus,
)
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.sender import QueuedEmailSender
from app.modules.email_outbox.service import EmailOutbox, EmailOutboxWorker
from app.modules.users.model import User  # noqa: F401  (FK de created_by)
from app.shared.exceptions import (
    EmailLogNotFoundError,
    EmailNotCancellableError,
    EmailNotResendableError,
)

TEST_CONTEXT = {"sent_at": "2026-10-28T09:00:00-03:00"}
RESET_CONTEXT = {
    "user_name": "Maria",
    "reset_link": "https://exemplo.com/reset-password?token=SEGREDO",
    "expire_minutes": 30,
}


@pytest.fixture
def outbox(db):
    return EmailOutbox(EmailOutboxRepository(db))


@pytest.fixture
def logs(outbox):
    return EmailLogService(outbox, get_settings())


def drain(db, provider=None) -> int:
    return EmailOutboxWorker(
        EmailOutboxRepository(db),
        EmailRenderer(StaticBrandingProvider()),
        provider or FakeEmailService(),
        get_settings(),
    ).run_once()


def search(logs, **filters):
    params = {
        "start": None,
        "end": None,
        "status": None,
        "template": None,
        "search": None,
        "related_type": None,
        "related_id": None,
        "page": 1,
        "limit": 20,
    }
    params.update(filters)
    return logs.search(**params)


class TestList:
    def test_filters_by_status_type_and_search(self, db, outbox, logs):
        sender = QueuedEmailSender(outbox)
        sender.send("test", dict(TEST_CONTEXT), "ana@test.com")
        sender.send("test", dict(TEST_CONTEXT), "bruno@test.com")
        sender.send("password_reset", dict(RESET_CONTEXT), "ana@test.com")
        drain(db)

        assert search(logs)[1] == 3
        assert search(logs, search="ana")[1] == 2
        assert search(logs, template="password_reset")[1] == 1
        assert search(logs, status=EmailStatus.SENT)[1] == 3
        assert search(logs, status=EmailStatus.DEAD)[1] == 0

    def test_notification_type_matches_all_notifications(self, db, outbox, logs):
        outbox.enqueue(
            "notification.task_assigned",
            {"task_id": 7, "task_title": "Revisar"},
            "a@test.com",
        )
        db.commit()

        assert search(logs, template="notification")[1] == 1

    def test_filters_by_period_and_related(self, db, outbox, logs):
        item = outbox.enqueue(
            "test", dict(TEST_CONTEXT), "a@test.com", related=("payment", 7)
        )
        item.created_at = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)
        outbox.enqueue("test", dict(TEST_CONTEXT), "b@test.com")
        db.commit()

        september = search(logs, start=date(2026, 9, 1), end=date(2026, 9, 30))
        assert [i.id for i in september[0]] == [item.id]
        assert search(logs, related_type="payment", related_id=7)[1] == 1

    def test_paginates(self, db, outbox, logs):
        for n in range(5):
            outbox.enqueue("test", dict(TEST_CONTEXT), f"{n}@test.com")
        db.commit()

        items, total = search(logs, page=2, limit=2)
        assert total == 5
        assert len(items) == 2


class TestDetail:
    def test_has_timeline_and_masked_html(self, db, outbox, logs):
        item = QueuedEmailSender(outbox).send(
            "password_reset", dict(RESET_CONTEXT), "maria@test.com"
        )
        drain(
            db,
            FakeEmailService(
                EmailSendError(
                    "timeout", transient=True, failover=True, provider="smtp"
                )
            ),
        )

        detail = logs.detail(item.id)

        assert detail.timeline[0].success is False
        assert detail.timeline[0].error == "timeout"
        assert "SEGREDO" not in (detail.html or "")
        assert detail.resendable is False

    def test_unknown_id(self, logs):
        with pytest.raises(EmailLogNotFoundError):
            logs.detail("nao-existe")


class TestResendAndCancel:
    def test_resend_creates_new_item_pointing_to_original(self, db, outbox, logs):
        item = QueuedEmailSender(outbox).send("test", dict(TEST_CONTEXT), "a@test.com")
        drain(db)

        copy = logs.resend(item.id, admin_id=None)

        assert copy.id != item.id
        assert copy.resent_from_id == item.id
        assert copy.status == EmailStatus.PENDING

    def test_invite_and_reset_are_not_resent(self, db, outbox, logs):
        item = QueuedEmailSender(outbox).send(
            "password_reset", dict(RESET_CONTEXT), "maria@test.com"
        )
        drain(db)

        with pytest.raises(EmailNotResendableError):
            logs.resend(item.id, admin_id=None)

    def test_pending_is_not_resent(self, db, outbox, logs):
        item = QueuedEmailSender(outbox).send("test", dict(TEST_CONTEXT), "a@test.com")

        with pytest.raises(EmailNotResendableError):
            logs.resend(item.id, admin_id=None)

    def test_batch_resend_reports_skipped(self, db, outbox, logs):
        sender = QueuedEmailSender(outbox)
        ok_item = sender.send("test", dict(TEST_CONTEXT), "a@test.com")
        reset = sender.send("password_reset", dict(RESET_CONTEXT), "b@test.com")
        drain(db)

        result = logs.resend_many([ok_item.id, reset.id, "nao-existe"], admin_id=None)

        assert len(result.resent) == 1
        assert {s.id for s in result.skipped} == {reset.id, "nao-existe"}

    def test_cancel_only_pending_or_failed(self, db, outbox, logs):
        pending = QueuedEmailSender(outbox).send(
            "test", dict(TEST_CONTEXT), "a@test.com"
        )

        assert logs.cancel(pending.id).status == EmailStatus.CANCELLED
        with pytest.raises(EmailNotCancellableError):
            logs.cancel(pending.id)


class TestHealth:
    def test_counts_queue_rate_and_days(self, db, outbox, logs):
        sender = QueuedEmailSender(outbox)
        sender.send("test", dict(TEST_CONTEXT), "a@test.com")
        sender.send("test", dict(TEST_CONTEXT), "b@test.com")
        drain(db)
        sender.send("test", dict(TEST_CONTEXT), "c@test.com")

        health = logs.health()

        assert health.queue_pending == 1
        assert health.sent_24h == 2
        assert health.success_rate_24h == 1.0
        assert len(health.daily) == 30
        assert health.daily[-1].sent == 2

    def test_open_circuit_shows_alert_inside_system(self, db, logs):
        db.add(
            EmailProviderHealth(
                provider="smtp",
                state=BreakerState.OPEN,
                consecutive_failures=5,
                opened_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        health = logs.health()

        assert health.providers[0].state == BreakerState.OPEN
        assert any(a.kind == "circuit:smtp" for a in health.alerts)

    def test_old_pending_shows_backlog_alert(self, db, outbox, logs):
        item = QueuedEmailSender(outbox).send("test", dict(TEST_CONTEXT), "a@test.com")
        item.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()

        assert any(a.kind == "backlog" for a in logs.health().alerts)

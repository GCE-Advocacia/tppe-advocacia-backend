from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email_outbox.model import EmailOutboxItem
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.service import EmailOutbox, EmailOutboxWorker

URL = "/api/v1/email-logs"
MARK = "e2e-email-logs@test.com"


@pytest.fixture
def queued(db_session: Session):
    """Três e-mails de teste na fila; apagados no fim."""
    outbox = EmailOutbox(EmailOutboxRepository(db_session))
    items = [
        outbox.enqueue("test", {"sent_at": "2026-10-28T09:00:00-03:00"}, MARK)
        for _ in range(3)
    ]
    db_session.commit()
    ids = [i.id for i in items]
    yield ids
    db_session.rollback()
    db_session.execute(
        delete(EmailOutboxItem).where(
            (EmailOutboxItem.id.in_(ids)) | (EmailOutboxItem.resent_from_id.in_(ids))
        )
    )
    db_session.commit()


def test_user_cannot_see_email_logs(client, user_headers):
    assert client.get(URL, headers=user_headers).status_code == 403


def test_lists_with_search_and_status(client, admin_headers, queued):
    response = client.get(
        URL, params={"busca": MARK, "status": "PENDING"}, headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 3
    assert body["data"][0]["template_name"] == "E-mail de teste"


def test_invalid_period_is_rejected(client, admin_headers):
    response = client.get(
        URL, params={"inicio": "2026-10-10", "fim": "2026-10-01"}, headers=admin_headers
    )

    assert response.status_code == 400


def test_detail_cancel_and_resend(client, admin_headers, queued):
    email_id = queued[0]

    assert client.get(f"{URL}/{email_id}", headers=admin_headers).status_code == 200
    cancelled = client.post(f"{URL}/{email_id}/cancel", headers=admin_headers)
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert (
        client.post(f"{URL}/{email_id}/cancel", headers=admin_headers).status_code
        == 409
    )

    resent = client.post(f"{URL}/{email_id}/resend", headers=admin_headers)
    assert resent.status_code == 201
    assert resent.json()["data"]["resent_from_id"] == email_id


def test_health_and_types(client, admin_headers, queued):
    health = client.get(f"{URL}/health", headers=admin_headers).json()["data"]
    types = client.get(f"{URL}/types", headers=admin_headers).json()["data"]

    assert health["queue_pending"] >= 3
    assert len(health["daily"]) == 30
    assert any(t["id"] == "payment_reminder_d5" for t in types)


def test_two_workers_do_not_send_the_same_email(db_engine, queued):
    """SKIP LOCKED: duas sessões em paralelo pegam lotes diferentes."""
    emails = [FakeEmailService(), FakeEmailService()]
    settings = get_settings().model_copy(update={"email_rate_limit_per_minute": 0})

    def run(index: int) -> int:
        with Session(db_engine) as session:
            return EmailOutboxWorker(
                EmailOutboxRepository(session),
                EmailRenderer(StaticBrandingProvider()),
                emails[index],
                settings,
                worker_id=f"w{index}",
            ).run_once()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [0, 1]))

    delivered = [m for e in emails for m in e.messages if MARK in m.to]
    assert len(delivered) == 3
    assert len({m.headers["X-Email-Id"] for m in delivered}) == 3


def test_recurring_payment_via_api(client, admin_headers, db_session, admin_user):
    from app.modules.clients.model import Client
    from app.modules.clients.repository import ClientRepository
    from app.modules.payments.model import Payment

    customer = ClientRepository(db_session).create(name="Recorrente", cpf="11122233344")
    db_session.commit()
    try:
        response = client.post(
            "/api/v1/payments",
            json={
                "client_id": customer.id,
                "payment_date": "2099-01-31",
                "amount": "300.00",
                "recurrence_months": 3,
            },
            headers=admin_headers,
        )
        assert response.status_code == 201
        assert response.json()["installments"] == 3
        dates = sorted(
            p.payment_date.isoformat()
            for p in db_session.query(Payment).filter_by(client_id=customer.id)
        )
        assert dates == ["2099-01-31", "2099-02-28", "2099-03-31"]
    finally:
        db_session.rollback()
        db_session.execute(delete(Payment).where(Payment.client_id == customer.id))
        db_session.execute(delete(Client).where(Client.id == customer.id))
        db_session.commit()

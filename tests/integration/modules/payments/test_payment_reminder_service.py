from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.modules.clients.repository import ClientRepository
from app.modules.email.branding import StaticBrandingProvider
from app.modules.email.errors import EmailSendError
from app.modules.email.fake_service import FakeEmailService
from app.modules.email.renderer import EmailRenderer
from app.modules.email_outbox.model import EmailOutboxItem, EmailStatus
from app.modules.email_outbox.repository import EmailOutboxRepository
from app.modules.email_outbox.service import EmailOutboxWorker
from app.modules.payments.model import PaymentStatus, ReminderKind, ReminderStatus
from app.modules.payments.repository import PaymentReminderRepository, PaymentRepository
from app.modules.payments.service import PaymentReminderService
from app.modules.users.repository import UserRepository
from app.shared.types import Role

TODAY = date(2026, 10, 10)
IN_5_DAYS = TODAY + timedelta(days=5)
IN_6_DAYS = TODAY + timedelta(days=6)


@pytest.fixture
def user_id(db: Session) -> int:
    user = UserRepository(db).create(
        name="Admin", email="admin@test.com", hashed_password="h", role=Role.ADMIN
    )
    return user.id


@pytest.fixture
def client_id(db: Session) -> int:
    return ClientRepository(db).create(name="Maria", email="maria@test.com").id


@pytest.fixture
def service(db: Session) -> PaymentReminderService:
    return PaymentReminderService(db)


def make_payment(
    db: Session,
    client_id: int,
    user_id: int,
    payment_date: date,
    status: PaymentStatus = PaymentStatus.PENDING,
):
    return PaymentRepository(db).create(
        client_id=client_id,
        payment_date=payment_date,
        amount=Decimal("150.00"),
        description="Honorários",
        created_by=user_id,
        status=status,
    )


def run_worker(db: Session, service: PaymentReminderService, email) -> int:
    worker = EmailOutboxWorker(
        EmailOutboxRepository(db),
        EmailRenderer(StaticBrandingProvider()),
        email,
        get_settings(),
        on_finished=[service.sync_from_email],
    )
    return worker.run_once()


class TestPaymentReminderService:
    def test_enfileira_d_minus_5_e_d_zero_com_templates_corretos(
        self, db, service, client_id, user_id
    ):
        make_payment(db, client_id, user_id, TODAY)
        make_payment(db, client_id, user_id, IN_5_DAYS)
        email = FakeEmailService()

        results = service.dispatch(TODAY)
        run_worker(db, service, email)

        assert results == {"queued": 2, "no_email": 0}
        subjects = sorted(m.subject for m in email.messages)
        assert subjects == ["Aviso: Vencimento hoje", "Lembrete: Vencimento em 5 dias"]
        assert all(m.to == ["maria@test.com"] for m in email.messages)
        html = email.messages[0].html
        assert "Maria" in html
        assert "R$ 150,00" in html
        assert "Honorários" in html

    def test_nao_enfileira_em_d_minus_6(self, db, service, client_id, user_id):
        make_payment(db, client_id, user_id, IN_6_DAYS)

        assert service.dispatch(TODAY) == {"queued": 0, "no_email": 0}
        assert db.query(EmailOutboxItem).count() == 0

    def test_lembrete_e_email_entram_juntos_na_fila(
        self, db, service, client_id, user_id
    ):
        payment = make_payment(db, client_id, user_id, TODAY)

        service.dispatch(TODAY)

        reminder = PaymentReminderRepository(db).list_by_payment(payment.id)[0]
        item = db.get(EmailOutboxItem, reminder.email_outbox_id)
        assert reminder.status == ReminderStatus.QUEUED
        assert item.status == EmailStatus.PENDING
        assert (item.related_type, item.related_id) == ("payment", payment.id)

    def test_rodar_duas_vezes_no_mesmo_dia_enfileira_so_uma_vez(
        self, db, service, client_id, user_id
    ):
        make_payment(db, client_id, user_id, TODAY)

        assert service.dispatch(TODAY)["queued"] == 1
        assert service.dispatch(TODAY)["queued"] == 0
        assert db.query(EmailOutboxItem).count() == 1

    def test_envio_atualiza_lembrete_para_sent(self, db, service, client_id, user_id):
        payment = make_payment(db, client_id, user_id, TODAY)
        service.dispatch(TODAY)

        run_worker(db, service, FakeEmailService())

        reminder = PaymentReminderRepository(db).list_by_payment(payment.id)[0]
        assert reminder.status == ReminderStatus.SENT
        assert reminder.kind == ReminderKind.D_ZERO

    def test_falha_definitiva_grava_failed(self, db, service, client_id, user_id):
        payment = make_payment(db, client_id, user_id, TODAY)
        service.dispatch(TODAY)
        failing = FakeEmailService(
            fail_with=EmailSendError(
                "550 user unknown", transient=False, failover=False, provider="smtp"
            )
        )

        run_worker(db, service, failing)

        reminder = PaymentReminderRepository(db).list_by_payment(payment.id)[0]
        assert reminder.status == ReminderStatus.FAILED
        assert "550" in reminder.error_message

    def test_falha_passageira_continua_na_fila(self, db, service, client_id, user_id):
        payment = make_payment(db, client_id, user_id, TODAY)
        service.dispatch(TODAY)
        failing = FakeEmailService(
            fail_with=EmailSendError(
                "timeout", transient=True, failover=True, provider="smtp"
            )
        )

        run_worker(db, service, failing)

        reminder = PaymentReminderRepository(db).list_by_payment(payment.id)[0]
        assert reminder.status == ReminderStatus.QUEUED

    def test_cliente_sem_email_nao_envia_e_grava_no_email(self, db, service, user_id):
        client_no_email = ClientRepository(db).create(name="João", email=None).id
        payment = make_payment(db, client_no_email, user_id, TODAY)

        results = service.dispatch(TODAY)

        assert results == {"queued": 0, "no_email": 1}
        reminders = PaymentReminderRepository(db).list_by_payment(payment.id)
        assert reminders[0].status == ReminderStatus.NO_EMAIL
        assert db.query(EmailOutboxItem).count() == 0

    def test_pagamento_ja_pago_nao_envia(self, db, service, client_id, user_id):
        make_payment(db, client_id, user_id, TODAY, status=PaymentStatus.PAID)

        assert service.dispatch(TODAY)["queued"] == 0

    def test_contexto_tem_dias_restantes(self, db, service, client_id, user_id):
        make_payment(db, client_id, user_id, TODAY + timedelta(days=3))

        service.dispatch(TODAY)

        item = db.query(EmailOutboxItem).one()
        assert item.template_id == "payment_reminder_d5"
        assert item.context["days_left"] == 3

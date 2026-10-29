from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.modules.clients.repository import ClientRepository
from app.modules.payments.model import PaymentStatus, ReminderKind, ReminderStatus
from app.modules.payments.repository import PaymentRepository, PaymentReminderRepository
from app.modules.users.repository import UserRepository
from app.shared.types import Role

# Lembre-se de importar o caminho correto do seu serviço
from app.modules.payments.service import PaymentReminderService

TODAY = date(2026, 10, 10)
TOMORROW = TODAY + timedelta(days=1)
D_MINUS_2 = TODAY + timedelta(days=2)

class FakeEmailService:
    def __init__(self):
        self.sent_emails = []

    def send(self, to: str, subject: str, body: str):
        self.sent_emails.append({"to": to, "subject": subject, "body": body})

@pytest.fixture
def user_id(db: Session) -> int:
    user = UserRepository(db).create(
        name="Admin", email="admin@test.com", hashed_password="h", role=Role.ADMIN
    )
    return user.id

@pytest.fixture
def client_id(db: Session) -> int:
    return ClientRepository(db).create(name="Maria", email="maria@test.com").id

def make_payment(db: Session, client_id: int, user_id: int, payment_date: date, status: PaymentStatus = PaymentStatus.PENDING):
    return PaymentRepository(db).create(
        client_id=client_id,
        payment_date=payment_date,
        amount=Decimal("150.00"),
        description="Honorários",
        created_by=user_id,
        status=status,
    )

class TestPaymentReminderService:
    def test_envia_em_d_minus_1_e_d_zero_com_templates_corretos(self, db: Session, client_id: int, user_id: int):
        make_payment(db, client_id, user_id, TODAY)
        make_payment(db, client_id, user_id, TOMORROW)
        
        fake_email = FakeEmailService()
        service = PaymentReminderService(db, fake_email)
        
        results = service.dispatch(TODAY)
        
        assert results["sent"] == 2
        assert len(fake_email.sent_emails) == 2
        
        subjects = [email["subject"] for email in fake_email.sent_emails]
        assert "Aviso: Vencimento hoje" in subjects
        assert "Lembrete: Vencimento amanhã" in subjects
        assert fake_email.sent_emails[0]["to"] == "maria@test.com"

    def test_nao_envia_em_d_minus_2(self, db: Session, client_id: int, user_id: int):
        make_payment(db, client_id, user_id, D_MINUS_2)
        
        fake_email = FakeEmailService()
        service = PaymentReminderService(db, fake_email)
        
        results = service.dispatch(TODAY)
        
        assert results["sent"] == 0
        assert len(fake_email.sent_emails) == 0

    def test_rodar_duas_vezes_no_mesmo_dia_envia_so_uma_vez(self, db: Session, client_id: int, user_id: int):
        make_payment(db, client_id, user_id, TODAY)
        
        fake_email = FakeEmailService()
        service = PaymentReminderService(db, fake_email)
        
        # Primeira execução
        results_1 = service.dispatch(TODAY)
        assert results_1["sent"] == 1
        
        # Segunda execução logo em seguida
        results_2 = service.dispatch(TODAY)
        assert results_2["sent"] == 0
        assert len(fake_email.sent_emails) == 1

    def test_cliente_sem_email_nao_envia_e_grava_status_no_email(self, db: Session, user_id: int):
        client_no_email = ClientRepository(db).create(name="João", email=None).id
        
        # Capture o objeto pagamento
        payment = make_payment(db, client_no_email, user_id, TODAY)
        
        fake_email = FakeEmailService()
        service = PaymentReminderService(db, fake_email)
        
        results = service.dispatch(TODAY)
        
        assert results["sent"] == 0
        assert results["no_email"] == 1
        assert len(fake_email.sent_emails) == 0
        
        # Busque de forma blindada pelo método list_by_payment
        reminders = PaymentReminderRepository(db).list_by_payment(payment.id)
        assert reminders[0].status == ReminderStatus.NO_EMAIL

    def test_pagamento_ja_pago_nao_envia(self, db: Session, client_id: int, user_id: int):
        make_payment(db, client_id, user_id, TODAY, status=PaymentStatus.PAID)
        
        fake_email = FakeEmailService()
        service = PaymentReminderService(db, fake_email)
        
        results = service.dispatch(TODAY)
        
        assert results["sent"] == 0
        assert len(fake_email.sent_emails) == 0
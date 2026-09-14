import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.modules.finance.model import FinancialTransaction

INCOMES_URL = "/api/v1/finance/incomes"
EXPENSES_URL = "/api/v1/finance/expenses"
TRANSACTIONS_URL = "/api/v1/finance/transactions"


@pytest.fixture
def cleanup_transactions(db_session: Session, admin_user):
    # Depende de admin_user para ser finalizada ANTES da remoção do usuário
    # (FK created_by -> users.id).
    ids: list[int] = []
    yield ids
    db_session.execute(
        delete(FinancialTransaction).where(FinancialTransaction.id.in_(ids))
    )
    db_session.commit()


def transaction_payload(**kwargs) -> dict:
    payload = {
        "description": "Honorários contratuais",
        "amount": "1500.50",
        "transaction_date": "2099-01-10",
    }
    payload.update(kwargs)
    return payload


class TestCreateIncome:
    def test_requires_auth(self, client):
        response = client.post(INCOMES_URL, json=transaction_payload())
        assert response.status_code in (401, 403)

    def test_user_forbidden(self, client, user_headers):
        response = client.post(
            INCOMES_URL, json=transaction_payload(), headers=user_headers
        )
        assert response.status_code == 403

    def test_admin_creates_income(self, client, admin_headers, cleanup_transactions):
        response = client.post(
            INCOMES_URL, json=transaction_payload(), headers=admin_headers
        )

        assert response.status_code == 201
        data = response.json()["data"]
        cleanup_transactions.append(data["id"])
        assert data["type"] == "INCOME"
        assert data["amount"] == "1500.50"
        assert data["transaction_date"] == "2099-01-10"

    def test_rejects_non_positive_amount(self, client, admin_headers):
        response = client.post(
            INCOMES_URL, json=transaction_payload(amount="0"), headers=admin_headers
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestCreateExpense:
    def test_user_forbidden(self, client, user_headers):
        response = client.post(
            EXPENSES_URL, json=transaction_payload(), headers=user_headers
        )
        assert response.status_code == 403

    def test_admin_creates_expense(self, client, admin_headers, cleanup_transactions):
        response = client.post(
            EXPENSES_URL,
            json=transaction_payload(description="Aluguel", amount="3200.00"),
            headers=admin_headers,
        )

        assert response.status_code == 201
        data = response.json()["data"]
        cleanup_transactions.append(data["id"])
        assert data["type"] == "EXPENSE"
        assert data["amount"] == "3200.00"

    def test_rejects_negative_amount(self, client, admin_headers):
        response = client.post(
            EXPENSES_URL,
            json=transaction_payload(amount="-50.00"),
            headers=admin_headers,
        )

        assert response.status_code == 422


class TestListTransactions:
    def test_user_forbidden(self, client, user_headers):
        response = client.get(TRANSACTIONS_URL, headers=user_headers)
        assert response.status_code == 403

    def test_admin_lists_incomes_and_expenses(
        self, client, admin_headers, cleanup_transactions
    ):
        income = client.post(
            INCOMES_URL,
            json=transaction_payload(transaction_date="2099-12-30"),
            headers=admin_headers,
        ).json()["data"]
        expense = client.post(
            EXPENSES_URL,
            json=transaction_payload(amount="80.00", transaction_date="2099-12-31"),
            headers=admin_headers,
        ).json()["data"]
        cleanup_transactions.extend([income["id"], expense["id"]])

        response = client.get(f"{TRANSACTIONS_URL}?limit=100", headers=admin_headers)

        assert response.status_code == 200
        body = response.json()
        ids = [t["id"] for t in body["data"]]
        assert income["id"] in ids
        assert expense["id"] in ids
        assert body["meta"]["page"] == 1


class TestListTransactionsByPeriod:
    def test_filters_by_period(self, client, admin_headers, cleanup_transactions):
        january = client.post(
            INCOMES_URL,
            json=transaction_payload(transaction_date="2098-01-10"),
            headers=admin_headers,
        ).json()["data"]
        february = client.post(
            EXPENSES_URL,
            json=transaction_payload(transaction_date="2098-02-10"),
            headers=admin_headers,
        ).json()["data"]
        cleanup_transactions.extend([january["id"], february["id"]])

        response = client.get(
            f"{TRANSACTIONS_URL}?date_from=2098-02-01&date_to=2098-02-28&limit=100",
            headers=admin_headers,
        )

        assert response.status_code == 200
        ids = [t["id"] for t in response.json()["data"]]
        assert february["id"] in ids
        assert january["id"] not in ids

    def test_rejects_inverted_period(self, client, admin_headers):
        response = client.get(
            f"{TRANSACTIONS_URL}?date_from=2098-02-28&date_to=2098-02-01",
            headers=admin_headers,
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_FINANCIAL_PERIOD"

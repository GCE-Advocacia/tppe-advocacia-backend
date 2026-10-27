from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.modules.email.filters import brl, data_br, data_extenso, data_hora_br


@pytest.mark.parametrize(
    "value, expected",
    [
        (1234.56, "R$ 1.234,56"),
        (Decimal("150.00"), "R$ 150,00"),
        ("1000000", "R$ 1.000.000,00"),
        (0, "R$ 0,00"),
        (None, ""),
    ],
)
def test_brl(value, expected):
    assert brl(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        (date(2026, 10, 26), "26/10/2026"),
        ("2026-10-26", "26/10/2026"),
        (datetime(2026, 10, 26, 1, 0, tzinfo=timezone.utc), "25/10/2026"),
        ("2026-10-26T15:00:00Z", "26/10/2026"),
        ("não é data", "não é data"),
        (None, ""),
    ],
)
def test_data_br(value, expected):
    assert data_br(value) == expected


def test_data_hora_br_converts_to_brasilia():
    assert data_hora_br("2026-10-26T15:30:00Z") == "26/10/2026 às 12:30"
    assert data_hora_br("2026-10-26") == "26/10/2026"


def test_data_extenso():
    assert data_extenso(date(2026, 10, 26)) == "26 de outubro de 2026"
    assert data_extenso("2026-03-01") == "1 de março de 2026"

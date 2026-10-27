"""Filtros Jinja2 em PT-BR. Aceitam objetos ou strings ISO (contexto em JSON)."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

# Brasília não tem horário de verão desde 2019: offset fixo evita depender
# do tzdata do sistema operacional.
BRT = timezone(timedelta(hours=-3), "BRT")

_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def _to_datetime(value: object) -> date | datetime | None:
    if isinstance(value, datetime | date):
        return value
    if isinstance(value, str) and value.strip():
        raw = value.strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(raw) if "T" in raw or " " in raw else date.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _local(value: date | datetime) -> date | datetime:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(BRT)
    return value


def brl(value: object) -> str:
    """1234.56 -> 'R$ 1.234,56'."""
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def data_br(value: object) -> str:
    """Data no formato 26/10/2026."""
    parsed = _to_datetime(value)
    if parsed is None:
        return "" if value is None else str(value)
    return _local(parsed).strftime("%d/%m/%Y")


def data_hora_br(value: object) -> str:
    """Data e hora no horário de Brasília: 26/10/2026 às 14:30."""
    parsed = _to_datetime(value)
    if parsed is None:
        return "" if value is None else str(value)
    if not isinstance(parsed, datetime):
        return parsed.strftime("%d/%m/%Y")
    return _local(parsed).strftime("%d/%m/%Y às %H:%M")


def data_extenso(value: object) -> str:
    """26 de outubro de 2026."""
    parsed = _to_datetime(value)
    if parsed is None:
        return "" if value is None else str(value)
    parsed = _local(parsed)
    return f"{parsed.day} de {_MESES[parsed.month - 1]} de {parsed.year}"


FILTERS = {
    "brl": brl,
    "data_br": data_br,
    "data_hora_br": data_hora_br,
    "data_extenso": data_extenso,
}

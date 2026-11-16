"""Tokens de uso único (redefinição de senha, convite).

O token em texto só existe no link enviado por e-mail; o banco guarda o
SHA-256 dele. Quem guarda e consome (marca ``used_at``, limpa o hash) é o
service de cada fluxo: aqui fica só o que é igual nos dois.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone


class OneTimeTokenService:
    def __init__(self, nbytes: int = 32) -> None:
        self.nbytes = nbytes

    @staticmethod
    def hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def generate(self) -> tuple[str, str]:
        """Devolve ``(token, hash)``: o token vai no link, o hash no banco."""
        token = secrets.token_urlsafe(self.nbytes)
        return token, self.hash(token)

    @staticmethod
    def expires_at(ttl: timedelta, now: datetime | None = None) -> datetime:
        return (now or datetime.now(timezone.utc)) + ttl

    @staticmethod
    def is_expired(expires_at: datetime, now: datetime | None = None) -> bool:
        # SQLite (testes) devolve datetime sem fuso.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at <= (now or datetime.now(timezone.utc))

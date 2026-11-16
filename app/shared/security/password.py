"""Política de senha e emissão do JWT, usadas pelo login, pela redefinição
de senha e pelo aceite do convite."""

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from pydantic import Field

from app.config.settings import get_settings
from app.modules.users.model import User

PASSWORD_MIN_LENGTH = 8

# Mesma regra em todo lugar que define senha (reset e convite).
NewPassword = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def issue_access_token(user: User) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    token_data = {
        "sub": str(user.id),
        "role": user.role.value,
        "can_view_payments": user.can_view_payments,
        "exp": expire,
    }
    return jwt.encode(token_data, settings.jwt_secret_key, algorithm="HS256")

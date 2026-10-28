import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.config.settings import get_settings

_settings = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
    enabled=_settings.app_env in ("production", "staging"),
)


def user_key(request: Request) -> str:
    """Limite por usuário logado (``sub`` do JWT), e não por IP. Sem token
    válido, cai no IP; a rota recusa com 401 de qualquer forma."""
    auth = request.headers.get("Authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(
                token, _settings.jwt_secret_key, algorithms=["HS256"]
            )
            return f"user:{payload['sub']}"
        except (jwt.PyJWTError, KeyError):
            pass
    return get_remote_address(request)

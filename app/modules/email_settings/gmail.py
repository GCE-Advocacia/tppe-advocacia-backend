"""Conexão da conta Google do escritório para enviar pela Gmail API.

A conta conectada vira a conta própria (perfil primário, ``provider="gmail"``),
com o refresh token criptografado no lugar da senha. Daí em diante a cadeia de
envio, o failover para a conta do sistema e o status funcionam como no SMTP.
"""

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone

import httpx
import jwt

from app.config.settings import Settings
from app.modules.audit_logs.service import AuditLogService
from app.modules.email.gmail_provider import GMAIL_SEND_SCOPE
from app.modules.email_settings.configs import decrypt_secret, get_email_cipher
from app.modules.email_settings.model import PRIMARY, EmailProfile
from app.modules.email_settings.repository import EmailProfileRepository
from app.modules.google_calendar.oauth import GoogleOAuthFlow
from app.modules.users.repository import UserRepository
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import GmailNotConfiguredError
from app.shared.types import Role

logger = logging.getLogger(__name__)

GMAIL_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    GMAIL_SEND_SCOPE,
]
_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
_STATE_PURPOSE = "gmail"
_STATE_TTL_MINUTES = 10


class GmailConnectError(Exception):
    """Falha no callback; ``reason`` vai para a URL de volta da tela."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason


class GmailConnectService:
    def __init__(
        self,
        repository: EmailProfileRepository,
        users: UserRepository,
        audit: AuditLogService,
        settings: Settings,
        oauth: GoogleOAuthFlow | None,
    ) -> None:
        self.repository = repository
        self.users = users
        self.audit = audit
        self.settings = settings
        self.oauth = oauth

    @property
    def db(self):
        return self.repository.db

    @property
    def available(self) -> bool:
        return self.oauth is not None

    def build_auth_url(self, user_id: int) -> str:
        if self.oauth is None:
            raise GmailNotConfiguredError()
        return self.oauth.build_auth_url(self._encode_state(user_id))

    def handle_callback(self, code: str, state: str) -> EmailProfile:
        if self.oauth is None:
            raise GmailConnectError("error", "Gmail integration is not configured")

        user_id = self._decode_state(state)
        user = self.users.get_by_id(user_id)
        if user is None or user.role != Role.ADMIN or not user.is_active:
            raise GmailConnectError("error", "Only active administrators can connect")

        try:
            credentials = self.oauth.exchange(code)
        except Warning as exc:
            # O oauthlib avisa quando o Google devolve menos escopos que o pedido:
            # o admin desmarcou a permissão de enviar e-mails.
            raise GmailConnectError("permission", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise GmailConnectError("error", "Failed to exchange code") from exc

        if GMAIL_SEND_SCOPE not in _granted_scopes(credentials):
            raise GmailConnectError("permission", "gmail.send was not granted")
        if not credentials.refresh_token:
            raise GmailConnectError("error", "Google did not return a refresh token")
        email = _email_from_id_token(credentials.id_token)
        if not email:
            raise GmailConnectError("error", "Google did not return the account email")

        cipher = get_email_cipher(self.settings)
        with unit_of_work(self.db):
            profile = self._primary_for_update()
            changes = {
                "provider": {"de": profile.provider, "para": "gmail"},
                "conta": {"de": profile.username, "para": email},
            }
            self.repository.update(
                profile,
                {
                    "provider": "gmail",
                    "preset": None,
                    "host": None,
                    "port": None,
                    "security": "starttls",
                    "username": email,
                    "from_email": email,
                    "secret_encrypted": cipher.encrypt(credentials.refresh_token),
                    "is_active": True,
                    "last_tested_at": datetime.now(timezone.utc),
                    "last_test_ok": True,
                    "version": profile.version + 1,
                    "updated_by": user.id,
                },
            )
            self.audit.log_email_settings_updated("Gmail conectado", changes, user)
        # O token anterior não é revogado: na mesma conta, revogar derruba a
        # autorização inteira, inclusive o token novo.
        return profile

    def disconnect(self, performed_by) -> None:
        """Volta a enviar pela conta do sistema e revoga o acesso no Google."""
        with unit_of_work(self.db):
            profile = self.repository.get_for_update_primary()
            if profile is None or profile.provider != "gmail":
                return
            token = decrypt_secret(profile, self.settings)
            self.repository.update(
                profile,
                {
                    "provider": "smtp",
                    "is_active": False,
                    "secret_encrypted": None,
                    "username": None,
                    "from_email": None,
                    "last_test_ok": None,
                    "version": profile.version + 1,
                    "updated_by": performed_by.id,
                },
            )
            self.audit.log_email_settings_updated(
                "Gmail desconectado",
                {"conta": {"de": profile.username, "para": None}},
                performed_by,
            )
        if token:
            _revoke(token)

    def _primary_for_update(self) -> EmailProfile:
        profile = self.repository.get_for_update_primary()
        if profile is None:
            profile = EmailProfile(
                name="Primário", priority=PRIMARY, provider="smtp", version=1
            )
            self.db.add(profile)
            self.db.flush()
        return profile

    # ----- state assinado (CSRF + identifica o admin no callback) ----------

    def _state_secret(self) -> str:
        # Chave própria: o state aparece na URL e não pode valer como login.
        return hmac.new(
            self.settings.jwt_secret_key.encode(), b"gmail_oauth_state", hashlib.sha256
        ).hexdigest()

    def _encode_state(self, user_id: int) -> str:
        payload = {
            "sub": str(user_id),
            "purpose": _STATE_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MINUTES),
        }
        return jwt.encode(payload, self._state_secret(), algorithm="HS256")

    def _decode_state(self, state: str) -> int:
        try:
            data = jwt.decode(state, self._state_secret(), algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise GmailConnectError("error", "Invalid or expired state") from exc
        if data.get("purpose") != _STATE_PURPOSE:
            raise GmailConnectError("error", "Invalid state")
        return int(data["sub"])


def _granted_scopes(credentials) -> list[str]:
    granted = getattr(credentials, "granted_scopes", None) or credentials.scopes or []
    return granted.split() if isinstance(granted, str) else list(granted)


def _email_from_id_token(id_token: str | None) -> str | None:
    """O id_token veio direto do endpoint de token do Google, por TLS: o
    OpenID Connect dispensa conferir a assinatura nesse caso."""
    if not id_token:
        return None
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return None
    email = claims.get("email")
    return email if isinstance(email, str) and claims.get("email_verified") else None


def _revoke(token: str) -> None:
    """Falhas são ignoradas: a desconexão local vale mesmo assim."""
    try:
        httpx.post(_REVOKE_URI, data={"token": token}, timeout=10)
    except Exception:
        logger.warning("Could not revoke Gmail token", exc_info=True)


def build_gmail_connect_service(
    repository: EmailProfileRepository,
    users: UserRepository,
    audit: AuditLogService,
    settings: Settings,
) -> GmailConnectService:
    oauth = (
        GoogleOAuthFlow(
            settings,
            scopes=GMAIL_SCOPES,
            redirect_uri=settings.google_gmail_redirect_uri,
            include_granted_scopes=False,
        )
        if settings.google_gmail_configured
        else None
    )
    return GmailConnectService(repository, users, audit, settings, oauth)

import base64
import threading
import time
from dataclasses import dataclass

import httpx

from app.modules.email.errors import EmailSendError
from app.modules.email.mime import build_mime, ensure_size_limit
from app.modules.email.protocol import EmailMessage, SendResult

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
_TOKEN_URI = "https://oauth2.googleapis.com/token"  # public OAuth URL  # nosec B105
_SEND_URI = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
# Renova o token de acesso um pouco antes de vencer.
_EXPIRY_MARGIN_SECONDS = 60
# Motivos do 403 que são limite de envio, e não falta de permissão.
_RATE_LIMIT_REASONS = ("ratelimitexceeded", "userratelimitexceeded", "quotaexceeded")


@dataclass(frozen=True)
class GmailConfig:
    refresh_token: str
    client_id: str
    client_secret: str
    from_email: str
    from_name: str | None = None
    reply_to: str | None = None
    max_size_mb: int = 10
    timeout_seconds: float = 15.0


class GmailProvider:
    """Envia pela Gmail API (HTTPS), com a conta Google conectada pelo admin.

    Não usa as portas de SMTP, então funciona onde a hospedagem as bloqueia.
    """

    name = "gmail"

    def __init__(
        self,
        config: GmailConfig,
        name: str = "gmail",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.name = name
        self._transport = transport
        self._lock = threading.Lock()
        self._access_token: str | None = None
        self._expires_at = 0.0

    def _client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.config.timeout_seconds, transport=self._transport
        )

    def _token(self, client: httpx.Client) -> str:
        with self._lock:
            if self._access_token and time.monotonic() < self._expires_at:
                return self._access_token
            response = client.post(
                _TOKEN_URI,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.config.refresh_token,
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                },
            )
            if response.status_code != 200:
                raise self._token_error(response)
            data = response.json()
            self._access_token = data["access_token"]
            self._expires_at = (
                time.monotonic()
                + int(data.get("expires_in", 3600))
                - _EXPIRY_MARGIN_SECONDS
            )
            return self._access_token

    def _forget_token(self) -> None:
        with self._lock:
            self._access_token = None
            self._expires_at = 0.0

    def _raw(self, message: EmailMessage) -> str:
        mime = build_mime(
            message,
            self.config.from_email,
            self.config.from_name,
            default_reply_to=self.config.reply_to,
        )
        # Na Gmail API o envelope vem dos cabeçalhos: o Bcc precisa ir junto
        # (o Google o remove antes de entregar).
        if message.bcc:
            mime["Bcc"] = ", ".join(message.bcc)
        return base64.urlsafe_b64encode(mime.as_bytes()).decode()

    def deliver(self, message: EmailMessage) -> SendResult:
        ensure_size_limit(message, self.config.max_size_mb, self.name)
        raw = self._raw(message)
        started = time.monotonic()
        try:
            with self._client() as client:
                response = client.post(
                    _SEND_URI,
                    headers={"Authorization": f"Bearer {self._token(client)}"},
                    json={"raw": raw},
                )
        except httpx.HTTPError as exc:
            raise EmailSendError(
                f"Erro de rede: {exc!r}",
                transient=True,
                failover=True,
                provider=self.name,
            ) from exc
        if response.status_code >= 300:
            if response.status_code == 401:
                self._forget_token()
            raise self._send_error(response)
        return SendResult(
            provider=self.name,
            message_id=str(response.json().get("id", "")),
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    def _token_error(self, response: httpx.Response) -> EmailSendError:
        error = _json(response).get("error", "")
        if error in ("invalid_grant", "unauthorized_client", "invalid_client"):
            return EmailSendError(
                "Gmail 401: o acesso à conta Google foi revogado ou expirou. "
                "Conecte a conta de novo.",
                transient=False,
                failover=True,
                provider=self.name,
            )
        return EmailSendError(
            f"Gmail {response.status_code}: falha ao renovar o acesso ({error})",
            transient=True,
            failover=True,
            provider=self.name,
        )

    def _send_error(self, response: httpx.Response) -> EmailSendError:
        code = response.status_code
        error = _json(response).get("error", {})
        message = error.get("message", "") if isinstance(error, dict) else str(error)
        reasons = (
            [str(e.get("reason", "")).lower() for e in error.get("errors", [])]
            if isinstance(error, dict)
            else []
        )
        reason = f"Gmail {code}: {message}".strip()
        if code == 429 or code >= 500:
            return EmailSendError(
                reason, transient=True, failover=True, provider=self.name
            )
        if code == 403 and any(r in _RATE_LIMIT_REASONS for r in reasons):
            return EmailSendError(
                reason, transient=True, failover=True, provider=self.name
            )
        if code in (401, 403):
            return EmailSendError(
                reason, transient=False, failover=True, provider=self.name
            )
        # 400: a mensagem em si é inválida; outro provedor não resolve.
        return EmailSendError(
            reason, transient=False, failover=False, provider=self.name
        )


def _json(response: httpx.Response) -> dict:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}

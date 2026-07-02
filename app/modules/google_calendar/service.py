from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.modules.appointments.model import Appointment, AppointmentType
from app.modules.appointments.repository import AppointmentRepository
from app.modules.google_calendar.crypto import TokenCipher
from app.modules.google_calendar.oauth import GoogleOAuthFlow
from app.modules.google_calendar.protocol import GoogleCalendarClient
from app.modules.google_calendar.repository import GoogleCredentialRepository
from app.modules.google_calendar.schema import GooglePullResult, GoogleStatusRead
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import GoogleNotConfiguredError, GoogleNotConnectedError

logger = logging.getLogger(__name__)

# Ações de sincronização disparadas pelo módulo appointments.
SYNC_CREATE = "create"
SYNC_UPDATE = "update"
SYNC_DELETE = "delete"

_STATE_PURPOSE = "google_oauth"
_STATE_TTL_MINUTES = 10


class GoogleOAuthError(Exception):
    """Falha no fluxo OAuth do Google (state inválido, troca de code, etc.).

    Não é uma AppException: o callback a captura e redireciona o browser.
    """


class GoogleCalendarService:
    def __init__(
        self,
        repository: GoogleCredentialRepository,
        client: GoogleCalendarClient,
        oauth: GoogleOAuthFlow | None,
        cipher: TokenCipher | None,
        state_secret: str,
        appointments: AppointmentRepository | None = None,
    ) -> None:
        self.repository = repository
        self.client = client
        self.oauth = oauth
        self.cipher = cipher
        self.state_secret = state_secret
        self.appointments = appointments

    # ----- OAuth / conexão -------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """True quando o servidor tem as credenciais do Google configuradas."""
        return self.oauth is not None and self.cipher is not None

    def build_auth_url(self, user_id: int) -> str:
        if self.oauth is None:
            raise GoogleNotConfiguredError()
        return self.oauth.build_auth_url(self._encode_state(user_id))

    def handle_callback(self, code: str, state: str) -> int:
        """Processa o callback do Google. Retorna o user_id conectado.

        Levanta GoogleOAuthError em qualquer falha — o router converte
        num redirect para o frontend.
        """
        if self.oauth is None or self.cipher is None:
            raise GoogleOAuthError("Google integration is not configured")

        user_id = self._decode_state(state)
        try:
            refresh_token, scope = self.oauth.exchange_code(code)
        except Exception as exc:  # noqa: BLE001
            raise GoogleOAuthError("Failed to exchange authorization code") from exc

        if not refresh_token:
            raise GoogleOAuthError("Google did not return a refresh token")

        with unit_of_work(self.repository.db):
            self.repository.upsert(
                user_id=user_id,
                encrypted_refresh_token=self.cipher.encrypt(refresh_token),
                scope=scope,
            )
        return user_id

    def disconnect(self, user_id: int) -> None:
        """Remove a credencial local. Idempotente.

        Eventos já sincronizados permanecem no Google Calendar do usuário
        (não tentamos apagá-los — falharia e não deve bloquear nada).
        """
        with unit_of_work(self.repository.db):
            self.repository.delete_by_user(user_id)

    def get_status(self, user_id: int) -> GoogleStatusRead:
        credential = self.repository.get_by_user(user_id)
        if credential is None:
            return GoogleStatusRead(connected=False)
        return GoogleStatusRead(
            connected=True,
            connected_at=credential.connected_at,
            scope=credential.scope,
        )

    # ----- Sync de compromissos -------------------------------------------

    def sync_appointment(self, appointment: Appointment, action: str) -> str | None:
        """Reflete a operação no Google Calendar do dono do compromisso.

        Retorna o `google_event_id` a persistir, ou None quando não há nada
        a atualizar (não configurado, usuário não conectado, ação de delete
        ou falha). Nunca levanta exceção — falha do Google é só logada.
        """
        if self.cipher is None:
            return None

        credential = self.repository.get_by_user(appointment.created_by)
        if credential is None:
            return None

        try:
            refresh_token = self.cipher.decrypt(credential.encrypted_refresh_token)
            event = self._to_event(appointment)

            if action == SYNC_DELETE:
                if appointment.google_event_id:
                    self.client.delete_event(refresh_token, appointment.google_event_id)
                return None

            if action == SYNC_UPDATE and appointment.google_event_id:
                self.client.update_event(
                    refresh_token, appointment.google_event_id, event
                )
                return appointment.google_event_id

            # create, ou update de um compromisso ainda não sincronizado
            return self.client.create_event(refresh_token, event)
        except Exception:
            logger.exception(
                "Google Calendar sync failed appointment_id=%s action=%s",
                appointment.id,
                action,
            )
            return None

    # ----- Pull: Google -> sistema ----------------------------------------

    def pull_changes(self, user_id: int) -> GooglePullResult:
        """Importa mudanças do Google Calendar do usuário para o sistema.

        Sync incremental via `syncToken`. Cria/atualiza/apaga compromissos
        locais conforme os eventos vindos do Google. Grava direto no
        repository de appointments (não passa pelo AppointmentService), então
        NÃO reenvia nada de volta pro Google — sem loop.

        Levanta GoogleNotConfiguredError / GoogleNotConnectedError para o
        endpoint manual. O job trata conectividade antes de chamar.
        """
        if self.cipher is None or self.appointments is None:
            raise GoogleNotConfiguredError()

        credential = self.repository.get_by_user(user_id)
        if credential is None:
            raise GoogleNotConnectedError()

        refresh_token = self.cipher.decrypt(credential.encrypted_refresh_token)
        events, next_sync_token = self.client.list_events(
            refresh_token, credential.sync_token
        )

        result = GooglePullResult()
        with unit_of_work(self.repository.db):
            for event in events:
                self._apply_event(user_id, event, result)
            self.repository.update_sync_token(credential, next_sync_token)
        return result

    def _apply_event(self, user_id: int, event: dict, result: GooglePullResult) -> None:
        google_event_id = event.get("id")
        if not google_event_id:
            return

        existing = self.appointments.get_by_google_event_id(google_event_id, user_id)

        if event.get("status") == "cancelled":
            if existing is not None:
                self.appointments.delete(existing)
                result.deleted += 1
            return

        fields = self._from_event(event)
        if fields is None:  # evento sem horário utilizável — ignora
            return

        if existing is not None:
            self.appointments.update(existing, fields)
            result.updated += 1
        else:
            self.appointments.create_from_google(
                created_by=user_id,
                google_event_id=google_event_id,
                type=AppointmentType.OUTRO,
                **fields,
            )
            result.created += 1

    @staticmethod
    def _from_event(event: dict) -> dict | None:
        """Extrai (title, starts_at, duration_minutes, description, location).

        Suporta eventos com horário (`dateTime`) e de dia inteiro (`date`).
        Retorna None se não houver início utilizável.
        """
        start_raw = event.get("start") or {}
        end_raw = event.get("end") or {}

        start = GoogleCalendarService._parse_edge(start_raw)
        if start is None:
            return None
        end = GoogleCalendarService._parse_edge(end_raw)

        if "date" in start_raw and "dateTime" not in start_raw:
            duration_minutes = 30  # evento de dia inteiro
        elif end is not None and end > start:
            duration_minutes = int((end - start).total_seconds() // 60)
        else:
            duration_minutes = 60
        duration_minutes = max(1, duration_minutes)

        return {
            "title": (event.get("summary") or "").strip() or "(sem título)",
            "starts_at": start,
            "duration_minutes": duration_minutes,
            "description": event.get("description"),
            "location": event.get("location"),
        }

    @staticmethod
    def _parse_edge(edge: dict) -> datetime | None:
        raw = edge.get("dateTime") or edge.get("date")
        if not raw:
            return None
        value = datetime.fromisoformat(raw)
        if value.tzinfo is None:  # evento all-day ("2026-12-01")
            # Noon UTC evita que o dia vire para trás em fusos como UTC-3 (Brasil)
            value = value.replace(hour=12, tzinfo=timezone.utc)
        return value

    @staticmethod
    def _to_event(appointment: Appointment) -> dict:
        start = appointment.starts_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        end = start + timedelta(minutes=appointment.duration_minutes)
        return {
            "summary": appointment.title,
            "description": appointment.description or "",
            "location": appointment.location or "",
            "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end.isoformat(), "timeZone": "UTC"},
        }

    # ----- state assinado (CSRF + identifica o usuário no callback) --------

    def _encode_state(self, user_id: int) -> str:
        payload = {
            "sub": str(user_id),
            "purpose": _STATE_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MINUTES),
        }
        return jwt.encode(payload, self.state_secret, algorithm="HS256")

    def _decode_state(self, state: str) -> int:
        try:
            data = jwt.decode(state, self.state_secret, algorithms=["HS256"])
        except jwt.PyJWTError as exc:
            raise GoogleOAuthError("Invalid or expired OAuth state") from exc
        if data.get("purpose") != _STATE_PURPOSE:
            raise GoogleOAuthError("Invalid OAuth state")
        return int(data["sub"])


def build_google_calendar_service(
    db: Session, client: GoogleCalendarClient
) -> GoogleCalendarService:
    """Monta o GoogleCalendarService a partir das settings.

    Quando o Google não está configurado, `oauth`/`cipher` ficam None — o
    service ainda funciona: `status` responde desconectado e `sync` é no-op.
    """
    settings = get_settings()
    configured = settings.google_configured
    return GoogleCalendarService(
        repository=GoogleCredentialRepository(db),
        client=client,
        oauth=GoogleOAuthFlow(settings) if configured else None,
        cipher=(
            TokenCipher(settings.google_token_encryption_key) if configured else None
        ),
        state_secret=settings.jwt_secret_key,
        appointments=AppointmentRepository(db),
    )

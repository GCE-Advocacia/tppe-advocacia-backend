from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config.settings import Settings
from app.modules.audit_logs.service import AuditLogService
from app.modules.email.errors import EmailSendError
from app.modules.email.factory import OWN_ACCOUNT, build_provider
from app.modules.email.protocol import EmailMessage, EmailProvider, SendResult
from app.modules.email.renderer import EmailRenderer
from app.modules.email_outbox.model import (
    BreakerState,
    EmailAttempt,
    EmailOutboxItem,
    EmailProviderHealth,
    EmailStatus,
)
from app.modules.email_settings.configs import (
    decrypt_secret,
    form_to_config,
    get_email_cipher,
    profile_to_config,
)
from app.modules.email_settings.connection_test import (
    ConnectionTester,
    ConnectionTestReport,
)
from app.modules.email_settings.messages import explain_send_error
from app.modules.email_settings.model import PRIMARY, EmailIdentity, EmailProfile
from app.modules.email_settings.presets import PRESETS, get_preset, sender_warnings
from app.modules.email_settings.repository import EmailProfileRepository
from app.modules.email_settings.schema import (
    EmailIdentityUpdate,
    EmailProfileForm,
    EmailProfileUpdate,
    EmailStatusRead,
    TestSendMeRead,
)
from app.modules.users.model import User
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import (
    EmailProfileNotFoundError,
    EmailProfileTestFailedError,
    EmailProfileVersionConflictError,
    EmailTestSendFailedError,
)

# Campos comparados para a auditoria (o segredo é tratado à parte).
_AUDITED_FIELDS = (
    "name",
    "provider",
    "preset",
    "host",
    "port",
    "security",
    "username",
    "from_email",
    "from_name",
    "reply_to",
    "is_active",
)


class EmailSettingsService:
    def __init__(
        self,
        repository: EmailProfileRepository,
        tester: ConnectionTester,
        audit: AuditLogService,
        renderer: EmailRenderer,
        settings: Settings,
        email_service: Callable[[], EmailProvider] | None = None,
    ) -> None:
        self.repository = repository
        self.tester = tester
        self.audit = audit
        self.renderer = renderer
        self.settings = settings
        # Cadeia em uso (conta própria e conta do sistema), para o teste.
        self.email_service = email_service

    @property
    def db(self):
        return self.repository.db

    def list_profiles(self) -> list[EmailProfile]:
        """Só a conta própria: o antigo reserva não é mais editável."""
        primary = self.repository.get_primary()
        return [primary] if primary is not None else []

    def _get(self, profile_id: int) -> EmailProfile:
        profile = self.repository.get_by_id(profile_id)
        if profile is None or profile.priority != PRIMARY:
            raise EmailProfileNotFoundError()
        return profile

    @staticmethod
    def apply_preset(form: EmailProfileForm) -> EmailProfileForm:
        """Provedor da lista manda no servidor, na porta e na segurança. Sem
        remetente informado, usa o próprio e-mail da conta."""
        updates: dict = {}
        preset = get_preset(form.preset)
        if preset is not None and preset.id != "other":
            updates.update(host=preset.host, port=preset.port, security=preset.security)
        if not form.from_email and form.username and "@" in form.username:
            updates["from_email"] = form.username
        return form.model_copy(update=updates) if updates else form

    @staticmethod
    def warnings(profile: EmailProfile) -> list[str]:
        return sender_warnings(profile.from_email, profile.username, profile.preset)

    def test_connection(
        self, profile_id: int, form: EmailProfileForm
    ) -> ConnectionTestReport:
        """Testa o que está no formulário (ainda não salvo). Senha vazia usa
        a já salva no perfil."""
        profile = self._get(profile_id)
        form = self.apply_preset(form)
        stored = None if form.secret else decrypt_secret(profile, self.settings)
        return self.tester.test(
            form_to_config(form, stored, self.settings), get_preset(form.preset)
        )

    def update_profile(
        self, profile_id: int, payload: EmailProfileUpdate, updated_by: User
    ) -> EmailProfile:
        payload = self.apply_preset(payload)
        with unit_of_work(self.repository.db):
            profile = self.repository.get_for_update(profile_id)
            if profile is None or profile.priority != PRIMARY:
                raise EmailProfileNotFoundError()
            if profile.version != payload.version:
                raise EmailProfileVersionConflictError()

            secret_changed = bool(payload.secret)
            updates: dict = {
                field: getattr(payload, field)
                for field in _AUDITED_FIELDS
                if field != "name" or payload.name is not None
            }
            if secret_changed:
                updates["secret_encrypted"] = get_email_cipher(self.settings).encrypt(
                    payload.secret
                )

            # Perfil ativo só é salvo depois de passar no teste de conexão.
            # Desativar não precisa de teste.
            if payload.is_active:
                stored = (
                    None if secret_changed else decrypt_secret(profile, self.settings)
                )
                config = form_to_config(payload, stored, self.settings)
                report = self.tester.test(config, get_preset(payload.preset))
                updates["last_tested_at"] = datetime.now(timezone.utc)
                updates["last_test_ok"] = report.ok
                if not report.ok:
                    failed = report.first_error
                    raise EmailProfileTestFailedError(
                        failed.step, failed.error, failed.hint
                    )

            changes = {
                field: {"de": getattr(profile, field), "para": updates[field]}
                for field in _AUDITED_FIELDS
                if field in updates and getattr(profile, field) != updates[field]
            }
            if secret_changed:
                changes["secret"] = "alterado"

            # Nome e responder para agora ficam na identidade do escritório.
            for field in ("from_name", "reply_to"):
                changes.pop(field, None)
                updates.pop(field, None)
            if not changes:
                return profile

            updates["version"] = profile.version + 1
            updates["updated_by"] = updated_by.id
            updated = self.repository.update(profile, updates)
            self.audit.log_email_settings_updated(updated.name, changes, updated_by)
        return updated

    def test_send(self, profile_id: int, to: str, requested_by: User) -> SendResult:
        """Envia de verdade pelo perfil salvo (só ele, sem failover)."""
        profile = self._get(profile_id)
        provider = build_provider(profile_to_config(profile, self.settings))
        rendered = self.renderer.render(
            "test",
            {
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "requested_by": requested_by.name,
            },
        )
        try:
            return provider.deliver(
                EmailMessage(
                    to=[to],
                    subject=rendered.subject,
                    html=rendered.html,
                    text=rendered.text,
                )
            )
        except EmailSendError as err:
            explained = explain_send_error(err, get_preset(profile.preset))
            raise EmailTestSendFailedError(explained.message, explained.hint) from err

    # ---- identidade ---------------------------------------------------------

    def get_identity(self) -> EmailIdentity:
        identity = self.repository.get_identity()
        return identity if identity is not None else EmailIdentity(id=1, version=1)

    def update_identity(
        self, payload: EmailIdentityUpdate, updated_by: User
    ) -> EmailIdentity:
        with unit_of_work(self.db):
            identity = self.repository.get_identity_for_update()
            if identity.version != payload.version:
                raise EmailProfileVersionConflictError()
            updates = {"from_name": payload.from_name, "reply_to": payload.reply_to}
            changes = {
                field: {"de": getattr(identity, field), "para": value}
                for field, value in updates.items()
                if getattr(identity, field) != value
            }
            if not changes:
                return identity
            updates["version"] = identity.version + 1
            updates["updated_by"] = updated_by.id
            self.repository.update_identity(identity, updates)
            self.audit.log_email_settings_updated("Identidade", changes, updated_by)
        return identity

    # ---- status e teste -----------------------------------------------------

    def presets(self) -> list:
        return list(PRESETS.values())

    def system_account_email(self) -> str | None:
        if "smtp" in self.settings.email_providers and self.settings.smtp_from_email:
            return self.settings.smtp_from_email
        if self.settings.resend_api_key and self.settings.email_providers:
            return self.settings.resend_from_email
        return None

    def _health(self, provider: str) -> EmailProviderHealth | None:
        return self.db.get(EmailProviderHealth, provider)

    def status(self, now: datetime | None = None) -> EmailStatusRead:
        now = now or datetime.now(timezone.utc)
        identity = self.repository.get_identity()
        own = self.repository.get_own_account()
        own_health = self._health(OWN_ACCOUNT) if own is not None else None

        own_error: str | None = None
        if own is not None:
            if own.last_test_ok is False:
                own_error = "O último teste da sua conta falhou."
            elif own_health is not None and own_health.state != BreakerState.CLOSED:
                own_error = (
                    "Sua conta falhou várias vezes seguidas. Os e-mails estão "
                    "saindo pela conta do sistema."
                )
        account = "own" if own is not None and own_error is None else "system"
        account_email = (
            (own.from_email or own.username)
            if account == "own" and own
            else self.system_account_email()
        )

        last_sent_at = self.db.scalar(
            select(func.max(EmailOutboxItem.sent_at)).where(
                EmailOutboxItem.status == EmailStatus.SENT
            )
        )
        hour_ago = now - timedelta(hours=1)
        recent = self.db.execute(
            select(EmailAttempt.success, func.count())
            .where(EmailAttempt.created_at >= hour_ago)
            .group_by(EmailAttempt.success)
        ).all()
        counts = {bool(success): total for success, total in recent}
        dead_24h = (
            self.db.scalar(
                select(func.count(EmailOutboxItem.id)).where(
                    EmailOutboxItem.status == EmailStatus.DEAD,
                    EmailOutboxItem.created_at >= now - timedelta(hours=24),
                )
            )
            or 0
        )
        oldest = self.db.scalar(
            select(func.min(EmailOutboxItem.created_at)).where(
                EmailOutboxItem.status.in_(
                    (EmailStatus.PENDING, EmailStatus.FAILED, EmailStatus.SENDING)
                )
            )
        )
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        stuck = oldest is not None and now - oldest > timedelta(
            minutes=self.settings.email_backlog_alert_minutes
        )
        no_account = (
            own is None
            and self.system_account_email() is None
            and (self.settings.app_env == "production")
        )

        if no_account or stuck or (counts.get(False) and not counts.get(True)):
            state = "down"
            message = (
                "Os e-mails não estão saindo. O sistema continua tentando; "
                "confira a conta conectada ou fale com o suporte."
            )
        elif (
            own_error
            or dead_24h
            or (identity is not None and identity.last_test_ok is False)
        ):
            state = "degraded"
            message = own_error or (
                f"{dead_24h} e-mail(s) não foram entregues nas últimas 24 horas."
                if dead_24h
                else "O último e-mail de teste não foi enviado."
            )
        else:
            state = "ok"
            message = "Os e-mails estão saindo normalmente."

        return EmailStatusRead(
            state=state,
            message=message,
            account=account,
            account_email=account_email,
            own_account_configured=own is not None,
            own_account_error=own_error,
            last_sent_at=last_sent_at,
            last_test_at=identity.last_test_at if identity else None,
            last_test_ok=identity.last_test_ok if identity else None,
            last_test_error=identity.last_test_error if identity else None,
        )

    def test_send_me(self, requested_by: User) -> TestSendMeRead:
        """Envia agora, pela cadeia em uso, para o e-mail de quem pediu."""
        if self.email_service is None:
            raise RuntimeError("EmailSettingsService sem cadeia de envio")
        rendered = self.renderer.render(
            "test",
            {
                "sent_at": datetime.now(timezone.utc).isoformat(),
                "requested_by": requested_by.name,
            },
        )
        own = self.repository.get_own_account()
        error: EmailSendError | None = None
        result: SendResult | None = None
        try:
            result = self.email_service().deliver(
                EmailMessage(
                    to=[requested_by.email],
                    subject=rendered.subject,
                    html=rendered.html,
                    text=rendered.text,
                )
            )
        except EmailSendError as err:
            error = err

        explained = (
            explain_send_error(error, get_preset(own.preset) if own else None)
            if error is not None
            else None
        )
        with unit_of_work(self.db):
            identity = self.repository.get_identity_for_update()
            self.repository.update_identity(
                identity,
                {
                    "last_test_at": datetime.now(timezone.utc),
                    "last_test_ok": error is None,
                    "last_test_error": explained.message if explained else None,
                },
            )
        if explained is not None:
            raise EmailTestSendFailedError(explained.message, explained.hint)

        account = "own" if result.provider == OWN_ACCOUNT else "system"
        return TestSendMeRead(
            to=requested_by.email,
            account=account,
            fallback_used=own is not None and result.provider != OWN_ACCOUNT,
            duration_ms=result.duration_ms,
        )

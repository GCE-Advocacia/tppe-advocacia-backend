from datetime import datetime, timezone

from app.config.settings import Settings
from app.modules.audit_logs.service import AuditLogService
from app.modules.email.errors import EmailSendError
from app.modules.email.factory import build_provider
from app.modules.email.protocol import EmailMessage, SendResult
from app.modules.email.renderer import EmailRenderer
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
from app.modules.email_settings.model import EmailProfile
from app.modules.email_settings.repository import EmailProfileRepository
from app.modules.email_settings.schema import EmailProfileForm, EmailProfileUpdate
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
    ) -> None:
        self.repository = repository
        self.tester = tester
        self.audit = audit
        self.renderer = renderer
        self.settings = settings

    def list_profiles(self) -> list[EmailProfile]:
        return self.repository.list_all()

    def _get(self, profile_id: int) -> EmailProfile:
        profile = self.repository.get_by_id(profile_id)
        if profile is None:
            raise EmailProfileNotFoundError()
        return profile

    def test_connection(
        self, profile_id: int, form: EmailProfileForm
    ) -> ConnectionTestReport:
        """Testa o que está no formulário (ainda não salvo). Senha vazia usa
        a já salva no perfil."""
        profile = self._get(profile_id)
        stored = None if form.secret else decrypt_secret(profile, self.settings)
        return self.tester.test(form_to_config(form, stored, self.settings))

    def update_profile(
        self, profile_id: int, payload: EmailProfileUpdate, updated_by: User
    ) -> EmailProfile:
        with unit_of_work(self.repository.db):
            profile = self.repository.get_for_update(profile_id)
            if profile is None:
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
                report = self.tester.test(config)
                updates["last_tested_at"] = datetime.now(timezone.utc)
                updates["last_test_ok"] = report.ok
                if not report.ok:
                    failed = report.first_error
                    raise EmailProfileTestFailedError(failed.step, failed.error)

            changes = {
                field: {"de": getattr(profile, field), "para": updates[field]}
                for field in _AUDITED_FIELDS
                if field in updates and getattr(profile, field) != updates[field]
            }
            if secret_changed:
                changes["secret"] = "alterado"

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
            raise EmailTestSendFailedError(err.reason) from err

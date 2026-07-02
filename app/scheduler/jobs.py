"""Jobs executados pelo scheduler.

Cada job abre sua própria Session (fora do ciclo de request) e monta o
grafo de dependências necessário, seguindo o mesmo padrão de injeção
manual usado pelos controllers.
"""

import logging
from datetime import date

from app.config.settings import get_settings
from app.db.database import SessionLocal
from app.modules.datajud.datajud_service import DataJudApiService
from app.modules.datajud.schema import DataJudBatchSyncRequest
from app.modules.datajud.service import DataJudService
from app.modules.deadlines.repository import (
    DeadlineAlertRepository,
    DeadlineRepository,
)
from app.modules.deadlines.service import DeadlineService
from app.modules.email.resend_service import ResendEmailService
from app.modules.external_api_logs.notifier import ExternalApiFailureNotifier
from app.modules.external_api_logs.repository import ExternalApiLogRepository
from app.modules.forensic_holidays.repository import ForensicHolidayRepository
from app.modules.google_calendar.service import build_google_calendar_service
from app.modules.notifications.repository import NotificationPreferenceRepository
from app.modules.notifications.service import NotificationService
from app.modules.processes.repository import ProcessRepository
from app.modules.users.repository import UserRepository
from app.shared.deps.google import get_google_calendar_client

logger = logging.getLogger(__name__)


def dispatch_deadline_alerts_job() -> None:
    """Varre os prazos e dispara os alertas escalonados pendentes (US-28)."""
    logger.info("Deadline alerts job started")
    try:
        settings = get_settings()
        with SessionLocal() as db:
            notification_service = NotificationService(
                NotificationPreferenceRepository(db),
                UserRepository(db),
                ResendEmailService(),
            )
            service = DeadlineService(
                repository=DeadlineRepository(db),
                holiday_repository=ForensicHolidayRepository(db),
                process_repository=ProcessRepository(db),
                alert_repository=DeadlineAlertRepository(db),
                notification_service=notification_service,
                alert_intervals=settings.deadline_alert_intervals,
            )
            sent = service.dispatch_alerts(today=date.today())
        logger.info("Deadline alerts job finished — %d alert(s) sent", sent)
    except Exception:
        logger.exception("Deadline alerts job failed")


def dispatch_google_pull_job() -> None:
    """Importa mudanças do Google Calendar de cada usuário conectado.

    Sync incremental (syncToken). Falha de um usuário não interrompe os
    demais. No-op quando o Google não está configurado.
    """
    logger.info("Google Calendar pull job started")
    created = updated = deleted = 0
    try:
        with SessionLocal() as db:
            client = get_google_calendar_client()
            service = build_google_calendar_service(db, client)
            if not service.is_configured:
                logger.info("Google Calendar pull job skipped — not configured")
                return
            credentials = service.repository.list_all()
            for credential in credentials:
                try:
                    result = service.pull_changes(credential.user_id)
                    created += result.created
                    updated += result.updated
                    deleted += result.deleted
                except Exception:
                    logger.exception(
                        "Google Calendar pull failed user_id=%s",
                        credential.user_id,
                    )
        logger.info(
            "Google Calendar pull job finished — %d created, %d updated, %d deleted",
            created,
            updated,
            deleted,
        )
    except Exception:
        logger.exception("Google Calendar pull job failed")


def dispatch_datajud_sync_job() -> None:
    """Varre processos ativos e importa movimentações pelo DataJud (US-20)."""
    logger.info("DataJud sync job started")
    try:
        settings = get_settings()
        with SessionLocal() as db:
            users = UserRepository(db)
            notification_service = NotificationService(
                NotificationPreferenceRepository(db),
                users,
                ResendEmailService(),
            )
            log_repository = ExternalApiLogRepository(db)
            service = DataJudService(
                process_repository=ProcessRepository(db),
                log_repository=log_repository,
                datajud_client=DataJudApiService(),
                failure_notifier=ExternalApiFailureNotifier(
                    users,
                    notification_service,
                    log_repository,
                ),
            )
            result = service.sync_active_processes(
                DataJudBatchSyncRequest(limit=settings.datajud_sync_limit),
                actor_id=settings.datajud_sync_user_id,
            )
        logger.info(
            "DataJud sync job finished — %d success, %d failure, %d imported",
            result.success_count,
            result.failure_count,
            result.imported_count,
        )
    except Exception:
        logger.exception("DataJud sync job failed")

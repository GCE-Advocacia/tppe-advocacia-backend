"""Setup do APScheduler.

Roda um `BackgroundScheduler` (síncrono, coerente com as sessions
síncronas do SQLAlchemy usadas no projeto). Sem fila externa no MVP — o
disparo dos alertas acontece dentro do próprio job. Se ficar lento,
migrar para ARQ/Celery.

O horário do cron usa o fuso local do servidor.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config.settings import get_settings
from app.scheduler.jobs import (
    dispatch_datajud_sync_job,
    dispatch_deadline_alerts_job,
    dispatch_google_pull_job,
)

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> None:
    """Inicia o scheduler e registra os jobs. Idempotente."""
    global _scheduler

    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled (SCHEDULER_ENABLED=false)")
        return

    if _scheduler is not None and _scheduler.running:
        return

    hour, minute = settings.deadline_alert_cron_parts
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        dispatch_deadline_alerts_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="deadline_alerts",
        replace_existing=True,
    )
    _scheduler.add_job(
        dispatch_datajud_sync_job,
        trigger="interval",
        hours=settings.datajud_sync_interval_hours,
        id="datajud_sync",
        replace_existing=True,
    )
    _scheduler.add_job(
        dispatch_google_pull_job,
        trigger="interval",
        minutes=settings.google_pull_interval_minutes,
        id="google_pull",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Scheduler started — deadline alerts cron at %02d:%02d; "
        "DataJud sync every %dh; Google pull every %dmin",
        hour,
        minute,
        settings.datajud_sync_interval_hours,
        settings.google_pull_interval_minutes,
    )


def shutdown_scheduler() -> None:
    """Para o scheduler, se estiver rodando."""
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None

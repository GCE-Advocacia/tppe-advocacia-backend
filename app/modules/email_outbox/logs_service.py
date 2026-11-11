from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config.settings import Settings
from app.modules.email.registry import TEMPLATES
from app.modules.email_outbox.model import BreakerState, EmailOutboxItem, EmailStatus
from app.modules.email_outbox.schema import (
    DailyCount,
    EmailAlertRead,
    EmailAttemptRead,
    EmailHealthRead,
    EmailLogDetail,
    EmailLogRead,
    EmailTypeRead,
    ProviderHealthRead,
    ResendBatchResult,
    ResendBatchSkipped,
)
from app.modules.email_outbox.service import NOT_RESENDABLE, EmailOutbox
from app.shared.db.uow import unit_of_work
from app.shared.exceptions import AppException, EmailLogNotFoundError

# O escritório trabalha no horário de Brasília: período e gráfico por dia daqui.
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
HEALTH_DAYS = 30


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def template_name(template_id: str) -> str:
    spec = TEMPLATES.get(template_id)
    return spec.name if spec is not None else template_id


def _read(item: EmailOutboxItem) -> EmailLogRead:
    return EmailLogRead(
        id=item.id,
        template_id=item.template_id,
        template_name=template_name(item.template_id),
        to=list(item.to),
        subject=item.subject,
        status=item.status,
        attempts=item.attempts,
        provider=item.provider,
        last_error=item.last_error,
        related_type=item.related_type,
        related_id=item.related_id,
        resent_from_id=item.resent_from_id,
        resendable=item.template_id not in NOT_RESENDABLE
        and item.status not in (EmailStatus.PENDING, EmailStatus.SENDING)
        and bool(item.context or item.html),
        created_at=item.created_at,
        next_attempt_at=item.next_attempt_at,
        sent_at=item.sent_at,
    )


class EmailLogService:
    """Histórico e painel de saúde do e-mail (tela do admin)."""

    def __init__(self, outbox: EmailOutbox, settings: Settings) -> None:
        self.outbox = outbox
        self.repository = outbox.repository
        self.settings = settings

    @property
    def db(self):
        return self.repository.db

    def types(self) -> list[EmailTypeRead]:
        return [
            EmailTypeRead(id=spec.id, name=spec.name)
            for spec in sorted(TEMPLATES.values(), key=lambda s: s.name)
        ]

    def search(
        self,
        *,
        start: date | None,
        end: date | None,
        status: EmailStatus | None,
        template: str | None,
        search: str | None,
        related_type: str | None,
        related_id: int | None,
        page: int,
        limit: int,
    ) -> tuple[list[EmailLogRead], int]:
        items, total = self.repository.search(
            start=datetime.combine(start, time.min, LOCAL_TZ) if start else None,
            end=datetime.combine(end + timedelta(days=1), time.min, LOCAL_TZ)
            if end
            else None,
            status=status,
            template=template,
            search=search or None,
            related_type=related_type,
            related_id=related_id,
            page=page,
            limit=limit,
        )
        return [_read(item) for item in items], total

    def _get(self, email_id: str) -> EmailOutboxItem:
        item = self.repository.get(email_id)
        if item is None:
            raise EmailLogNotFoundError()
        return item

    def detail(self, email_id: str) -> EmailLogDetail:
        item = self._get(email_id)
        return EmailLogDetail(
            **_read(item).model_dump(),
            cc=list(item.cc or []),
            bcc=list(item.bcc or []),
            html=item.html,
            text=item.text,
            timeline=[
                EmailAttemptRead.model_validate(a)
                for a in self.repository.list_attempts(item.id)
            ],
        )

    def resend(self, email_id: str, admin_id: int) -> EmailLogRead:
        item = self._get(email_id)
        with unit_of_work(self.db):
            copy = self.outbox.resend(item, created_by=admin_id)
        return _read(copy)

    def resend_many(self, ids: list[str], admin_id: int) -> ResendBatchResult:
        found = {item.id: item for item in self.repository.list_by_ids(ids)}
        resent: list[str] = []
        skipped: list[ResendBatchSkipped] = []
        for email_id in dict.fromkeys(ids):
            item = found.get(email_id)
            if item is None:
                skipped.append(ResendBatchSkipped(id=email_id, reason="Não encontrado"))
                continue
            try:
                with unit_of_work(self.db):
                    copy = self.outbox.resend(item, created_by=admin_id)
            except AppException as exc:
                skipped.append(ResendBatchSkipped(id=email_id, reason=exc.message))
                continue
            resent.append(copy.id)
        return ResendBatchResult(resent=resent, skipped=skipped)

    def cancel(self, email_id: str) -> EmailLogRead:
        item = self._get(email_id)
        with unit_of_work(self.db):
            self.outbox.cancel(item)
        return _read(item)

    def health(self, now: datetime | None = None) -> EmailHealthRead:
        now = now or datetime.now(timezone.utc)
        today = now.astimezone(LOCAL_TZ).date()
        first_day = today - timedelta(days=HEALTH_DAYS - 1)
        items = self.repository.list_since(
            datetime.combine(first_day, time.min, LOCAL_TZ)
        )

        per_day: dict[date, Counter[EmailStatus]] = {}
        last_24h: list[EmailOutboxItem] = []
        for item in items:
            created = _aware(item.created_at)
            per_day.setdefault(created.astimezone(LOCAL_TZ).date(), Counter())[
                item.status
            ] += 1
            if created >= now - timedelta(hours=24):
                last_24h.append(item)

        sent = [i for i in last_24h if i.status == EmailStatus.SENT]
        dead = [i for i in last_24h if i.status == EmailStatus.DEAD]
        finished = len(sent) + len(dead)
        delays = [
            (_aware(i.sent_at) - _aware(i.created_at)).total_seconds()
            for i in sent
            if i.sent_at is not None
        ]
        providers = [
            ProviderHealthRead.model_validate(h)
            for h in self.repository.list_provider_health()
        ]
        pending = self.repository.count_unsent()
        oldest = self.repository.oldest_unsent_at()

        return EmailHealthRead(
            providers=providers,
            queue_pending=pending,
            oldest_pending_at=oldest,
            success_rate_24h=round(len(sent) / finished, 4) if finished else None,
            avg_delivery_seconds_24h=round(sum(delays) / len(delays), 1)
            if delays
            else None,
            sent_24h=len(sent),
            dead_24h=len(dead),
            daily=[
                DailyCount(
                    day=day,
                    sent=per_day.get(day, Counter())[EmailStatus.SENT],
                    failed=per_day.get(day, Counter())[EmailStatus.FAILED],
                    dead=per_day.get(day, Counter())[EmailStatus.DEAD],
                )
                for day in (first_day + timedelta(days=n) for n in range(HEALTH_DAYS))
            ],
            alerts=self._alerts(providers, pending, oldest, len(dead), now),
        )

    def _alerts(
        self,
        providers: list[ProviderHealthRead],
        pending: int,
        oldest: datetime | None,
        dead_24h: int,
        now: datetime,
    ) -> list[EmailAlertRead]:
        """Os mesmos avisos que vão por e-mail, calculados na hora: se o SMTP
        está fora, o admin ainda vê o problema dentro do sistema."""
        alerts: list[EmailAlertRead] = []
        for provider in providers:
            if provider.state == BreakerState.OPEN:
                alerts.append(
                    EmailAlertRead(
                        kind=f"circuit:{provider.provider}",
                        level="critical",
                        message=f"Provedor {provider.provider} pausado após "
                        f"{provider.consecutive_failures} falhas seguidas.",
                    )
                )
        if dead_24h:
            alerts.append(
                EmailAlertRead(
                    kind="dead",
                    level="critical",
                    message=f"{dead_24h} e-mail(s) não entregues nas últimas 24 horas.",
                )
            )
        backlog_age = timedelta(minutes=self.settings.email_backlog_alert_minutes)
        if oldest is not None and now - _aware(oldest) > backlog_age:
            alerts.append(
                EmailAlertRead(
                    kind="backlog",
                    level="critical"
                    if pending >= self.settings.email_backlog_alert_size
                    else "warning",
                    message=f"{pending} e-mail(s) na fila; o mais antigo aguarda "
                    f"há {int((now - _aware(oldest)).total_seconds() // 60)} minutos.",
                )
            )
        return alerts

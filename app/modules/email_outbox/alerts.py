import logging
from datetime import datetime, timedelta

from app.config.settings import Settings
from app.modules.email_outbox.model import EmailAlertLog, EmailOutboxItem
from app.modules.email_outbox.service import EmailOutbox
from app.modules.users.repository import UserRepository
from app.shared.types import Role

logger = logging.getLogger(__name__)

ALERT_TEMPLATE = "email_alert"


class EmailAlerts:
    """Avisa os admins por e-mail quando o envio para, com limite de
    frequência por tipo de alerta. Se o SMTP está fora, o aviso fica na fila;
    o painel de saúde mostra o mesmo alerta dentro do sistema."""

    def __init__(
        self, outbox: EmailOutbox, users: UserRepository, settings: Settings
    ) -> None:
        self.outbox = outbox
        self.users = users
        self.throttle = timedelta(minutes=settings.email_alert_throttle_minutes)
        self.backlog_size = settings.email_backlog_alert_size
        self.backlog_age = timedelta(minutes=settings.email_backlog_alert_minutes)

    @property
    def db(self):
        return self.outbox.repository.db

    def check(
        self, *, dead: list[EmailOutboxItem], opened: list[str], now: datetime
    ) -> list[str]:
        """Dispara o que for preciso e devolve os tipos avisados. Não comita."""
        sent: list[str] = []
        # Aviso que morreu não gera outro aviso (evita laço quando o SMTP cai).
        dead = [item for item in dead if item.template_id != ALERT_TEMPLATE]
        if dead:
            recipients = ", ".join(sorted({to for item in dead for to in item.to}))
            if self._alert(
                "dead",
                "E-mail não entregue",
                f"{len(dead)} e-mail(s) esgotaram as tentativas e não foram "
                f"entregues. Destinatários: {recipients}.",
                now,
            ):
                sent.append("dead")
        for provider in opened:
            kind = f"circuit:{provider}"
            if self._alert(
                kind,
                f"Provedor de e-mail pausado: {provider}",
                f"O provedor {provider} falhou várias vezes seguidas e foi "
                "pausado. Os e-mails seguem pelo reserva, se houver, e o "
                "sistema volta a testar o provedor sozinho.",
                now,
            ):
                sent.append(kind)
        backlog = self.outbox.repository.count_backlog(now - self.backlog_age)
        if backlog >= self.backlog_size and self._alert(
            "backlog",
            "Fila de e-mails acumulada",
            f"{backlog} e-mail(s) aguardam envio há mais de "
            f"{int(self.backlog_age.total_seconds() // 60)} minutos.",
            now,
        ):
            sent.append("backlog")
        return sent

    def _alert(self, kind: str, title: str, detail: str, now: datetime) -> bool:
        log = self.db.get(EmailAlertLog, kind)
        if log is not None and self.throttle.total_seconds() > 0:
            last = log.last_alert_at
            if last.tzinfo is None:
                last = last.replace(tzinfo=now.tzinfo)
            if now - last < self.throttle:
                return False
        if log is None:
            log = EmailAlertLog(kind=kind, last_alert_at=now)
            self.db.add(log)
        else:
            log.last_alert_at = now

        admins, _ = self.users.get_all(
            role=Role.ADMIN, is_active=True, page=1, limit=1000
        )
        for admin in admins:
            self.outbox.enqueue(
                ALERT_TEMPLATE,
                {"title": title, "detail": detail, "occurred_at": now.isoformat()},
                to=admin.email,
                related=("user", admin.id),
            )
        logger.warning("Email alert %s sent to %d admin(s)", kind, len(admins))
        self.db.flush()
        return True

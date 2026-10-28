"""Catálogo dos tipos de e-mail: fonte única para o renderer, a
pré-visualização e os testes.

Cada tipo tem ``<id>.html`` e ``<id>.txt`` em ``templates/`` (``.`` no id vira
``/``: ``notification.task_assigned`` -> ``notification/task_assigned.html``).
``defaults`` lista as chaves opcionais do contexto: como o renderer usa
``StrictUndefined``, qualquer outra chave que faltar quebra na hora.
"""

from dataclasses import dataclass, field

from app.modules.notifications.schema import EventType


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    name: str
    description: str
    subject: str
    sample_context: dict
    defaults: dict = field(default_factory=dict)

    @property
    def path(self) -> str:
        return self.id.replace(".", "/")


def notification_template_id(event_type: EventType) -> str:
    return f"notification.{event_type.value.lower()}"


_SPECS = [
    TemplateSpec(
        id="password_reset",
        name="Redefinição de senha",
        description="Link para o usuário criar uma nova senha.",
        subject="Redefinição de senha",
        sample_context={
            "user_name": "Maria Souza",
            "reset_link": "https://exemplo.com/reset-password?token=EXEMPLO",
            "expire_minutes": 30,
        },
    ),
    TemplateSpec(
        id="user_invite",
        name="Convite de usuário",
        description="Convite para o funcionário definir a própria senha.",
        subject="Você foi convidado para o sistema do {{ office.name }}",
        sample_context={
            "user_name": "João Lima",
            "invite_link": "https://exemplo.com/convite/EXEMPLO",
            "expires_at": "2026-10-28T14:30:00-03:00",
        },
        defaults={"invited_by": None},
    ),
    TemplateSpec(
        id="payment_reminder_d5",
        name="Lembrete de pagamento (antecedência)",
        description="Enviado ao cliente cinco dias antes do vencimento.",
        subject=(
            "Lembrete: Vencimento "
            "{{ 'amanhã' if days_left == 1 else 'em ' ~ days_left ~ ' dias' }}"
        ),
        sample_context={
            "client_name": "Ana Pereira",
            "description": "Honorários advocatícios",
            "amount": "1500.00",
            "due_date": "2026-10-31",
            "days_left": 5,
        },
        defaults={"description": None, "amount": None},
    ),
    TemplateSpec(
        id="payment_reminder_d1",
        name="Lembrete de pagamento (véspera)",
        description="Antigo lembrete da véspera; mantido para o histórico.",
        subject="Lembrete: Vencimento amanhã",
        sample_context={
            "client_name": "Ana Pereira",
            "description": "Honorários advocatícios",
            "amount": "1500.00",
            "due_date": "2026-10-27",
        },
        defaults={"description": None, "amount": None},
    ),
    TemplateSpec(
        id="payment_reminder_d0",
        name="Lembrete de pagamento (dia do vencimento)",
        description="Enviado ao cliente no dia do vencimento.",
        subject="Aviso: Vencimento hoje",
        sample_context={
            "client_name": "Ana Pereira",
            "description": "Honorários advocatícios",
            "amount": "1500.00",
            "due_date": "2026-10-26",
        },
        defaults={"description": None, "amount": None},
    ),
    TemplateSpec(
        id="email_alert",
        name="Alerta de envio de e-mail",
        description="Avisa os administradores quando o envio de e-mail para.",
        subject="Alerta do sistema: {{ title }}",
        sample_context={
            "title": "Provedor de e-mail pausado: smtp",
            "detail": "O provedor smtp falhou várias vezes seguidas e foi pausado.",
            "occurred_at": "2026-10-28T10:00:00-03:00",
        },
    ),
    TemplateSpec(
        id="test",
        name="E-mail de teste",
        description="Usado para testar a configuração de envio.",
        subject="E-mail de teste do {{ office.name }}",
        sample_context={"sent_at": "2026-10-26T10:00:00-03:00"},
        defaults={"requested_by": None},
    ),
    TemplateSpec(
        id=notification_template_id(EventType.PROCESS_MOVEMENT_CREATED),
        name="Nova movimentação processual",
        description="Movimentação registrada em um processo.",
        subject="Nova movimentação no processo {{ process_number }}",
        sample_context={
            "process_number": "1234567-89.2024.8.26.0100",
            "title": "Petição inicial protocolada",
            "description": "Juntada de documentos pela parte autora.",
            "occurred_at": "2026-10-26T09:00:00Z",
        },
        defaults={"description": None},
    ),
    TemplateSpec(
        id=notification_template_id(EventType.PROCESS_STATUS_CHANGED),
        name="Status do processo alterado",
        description="Mudança de status de um processo.",
        subject="Status do processo {{ process_number }} alterado",
        sample_context={
            "process_number": "1234567-89.2024.8.26.0100",
            "previous_status": "ATIVO",
            "new_status": "SUSPENSO",
            "reason": "Aguardando perícia.",
        },
        defaults={"reason": None},
    ),
    TemplateSpec(
        id=notification_template_id(EventType.LEAD_ASSIGNED),
        name="Lead atribuído",
        description="Um lead foi atribuído ao usuário.",
        subject="Você foi atribuído ao lead #{{ lead_id }} - {{ lead_name }}",
        sample_context={
            "lead_id": 42,
            "lead_name": "Carlos Mendes",
            "lead_email": "carlos@exemplo.com",
            "lead_phone": "(61) 99999-0000",
        },
        defaults={"lead_phone": None},
    ),
    TemplateSpec(
        id=notification_template_id(EventType.TASK_ASSIGNED),
        name="Tarefa atribuída",
        description="Uma tarefa foi atribuída ao usuário.",
        subject="Nova tarefa atribuída: {{ task_title }}",
        sample_context={
            "task_id": 7,
            "task_title": "Revisar contrato social",
            "due_date": "2026-10-30",
        },
        defaults={"due_date": None},
    ),
    TemplateSpec(
        id=notification_template_id(EventType.DEADLINE_APPROACHING),
        name="Prazo se aproximando",
        description="Alerta escalonado antes do vencimento de um prazo.",
        subject="Prazo se aproximando: {{ deadline_type }} ({{ process_number }})",
        sample_context={
            "process_number": "1234567-89.2024.8.26.0100",
            "deadline_type": "Contestação",
            "due_date": "2026-11-03",
            "business_days_left": 3,
        },
    ),
    TemplateSpec(
        id=notification_template_id(EventType.DEADLINE_EXPIRED),
        name="Prazo vencido",
        description="Aviso de prazo que venceu.",
        subject="Prazo VENCIDO: {{ deadline_type }} ({{ process_number }})",
        sample_context={
            "process_number": "1234567-89.2024.8.26.0100",
            "deadline_type": "Contestação",
            "due_date": "2026-10-24",
        },
    ),
    TemplateSpec(
        id=notification_template_id(EventType.EXTERNAL_API_FAILURE),
        name="Falha em integração externa",
        description="Uma chamada a uma API externa (ex.: DataJud) falhou.",
        subject="Falha em integração externa: {{ provider }}",
        sample_context={
            "provider": "DATAJUD",
            "operation": "sync_process",
            "http_status": 503,
            "error_code": "SERVICE_UNAVAILABLE",
            "error_message": "Serviço temporariamente indisponível",
            "request_identifier": "1234567-89.2024.8.26.0100",
            "tribunal_alias": "tjsp",
        },
        defaults={
            "http_status": None,
            "error_code": None,
            "error_message": None,
            "request_identifier": None,
            "tribunal_alias": None,
        },
    ),
]

TEMPLATES: dict[str, TemplateSpec] = {spec.id: spec for spec in _SPECS}

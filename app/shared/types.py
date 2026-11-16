import enum


class Role(enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class PermissionKey(str, enum.Enum):
    """Abas da área do sistema liberáveis para usuários USER, na ordem do menu."""

    LANDING_PAGE = "landing_page"
    ARTIGOS = "artigos"
    LEADS = "leads"
    CLIENTES = "clientes"
    AGENDA = "agenda"
    PAGAMENTOS = "pagamentos"
    PROCESSOS = "processos"
    TAREFAS = "tarefas"
    NOTIFICACOES = "notificacoes"
    LOGS_API = "logs_api"
    FERIADOS = "feriados"
    FINANCEIRO = "financeiro"

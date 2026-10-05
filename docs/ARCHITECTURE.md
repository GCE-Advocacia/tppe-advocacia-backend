# Arquitetura

Este projeto segue o padrão **Modular Monolith** com camadas internas por módulo. Cada domínio (users, leads, auth, health) é uma pasta autônoma com suas próprias camadas — model, schema, repository, service, deps e router. Código verdadeiramente compartilhado entre módulos fica em `shared/`.

---

## Estrutura de pastas

```
app/
├── main.py                        # ponto de entrada da aplicação
├── config/
│   └── settings.py                # configurações e variáveis de ambiente
├── db/
│   └── database.py                # conexão com o banco de dados
├── scheduler/                     # APScheduler — jobs agendados (cron)
│   ├── scheduler.py               # setup/start/shutdown do BackgroundScheduler
│   └── jobs.py                    # deadline alerts + DataJud sync jobs
├── shared/                        # código transversal entre módulos
│   ├── db/
│   │   ├── base_model.py          # DeclarativeBase do SQLAlchemy
│   │   └── uow.py                 # unit_of_work para transações
│   ├── deps/
│   │   ├── auth.py                # dependências de autenticação (get_current_user, require_admin)
│   │   ├── email.py               # injeção de EmailService
│   │   └── google.py              # injeção de GoogleCalendarClient
│   ├── http/
│   │   └── responses.py           # envelope padrão de resposta da API
│   ├── service/
│   │   └── helpers.py             # utilitários compartilhados entre services
│   ├── exceptions.py              # exceções customizadas (AppException e subclasses)
│   ├── datajud.py                 # utilitários para integração DataJud
│   └── types.py                   # tipos compartilhados e type aliases
├── modules/
│   ├── users/                     # domínio de usuários
│   │   ├── model.py               # ORM: User, Role
│   │   ├── schema.py              # DTOs: UserCreate, UserRead, UserUpdate
│   │   ├── repository.py          # queries de usuário
│   │   ├── service.py             # regras de negócio de usuário
│   │   ├── deps.py                # get_user_service() — factory injetável via Depends
│   │   └── router.py              # rotas HTTP /users
│   ├── leads/                     # domínio de leads
│   │   ├── model.py
│   │   ├── schema.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   └── router.py
│   ├── auth/                      # autenticação
│   │   ├── schema.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   └── router.py
│   ├── office_config/             # configurações institucionais
│   │   ├── model.py
│   │   ├── schema.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   └── router.py
│   ├── articles/                  # base de conhecimento / blog
│   │   ├── model.py               # ORM: Article
│   │   ├── schema.py              # ArticleCreate, ArticleUpdate, ArticleRead, ArticleListItem
│   │   ├── repository.py
│   │   ├── service.py             # CRUD + listagem paginada (published / all)
│   │   ├── deps.py
│   │   └── router.py              # /articles (público), /articles/admin (autenticado)
│   ├── audit_logs/                # log de auditoria
│   │   ├── model.py
│   │   ├── schema.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   └── router.py
│   ├── media/                     # upload e servimento de arquivos
│   │   ├── schema.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   ├── router.py
│   │   └── storage/
│   │       ├── protocol.py        # StorageProvider (Protocol)
│   │       └── local.py           # LocalStorageProvider
│   ├── email/                     # envio de e-mail
│   │   ├── protocol.py            # EmailService (Protocol)
│   │   ├── resend_service.py      # implementação Resend
│   │   └── fake_service.py        # implementação fake para testes
│   ├── clients/                   # gestão de clientes (PF e PJ)
│   │   ├── model.py               # ORM: Client, ClientNote
│   │   ├── schema.py              # ClientCreate/Update/Read, ClientNoteCreate/Update/Read, ClientTimelineRead
│   │   ├── repository.py
│   │   ├── timeline_repository.py # queries agregadas para a visão 360º do cliente
│   │   ├── service.py             # CRUD + anonimização LGPD + notas
│   │   ├── timeline_service.py    # monta o feed de atividades do cliente
│   │   ├── deps.py                # get_client_service(), get_client_timeline_service()
│   │   └── router.py              # /clients, /clients/{id}, /clients/{id}/notes, /clients/{id}/timeline
│   ├── datajud/                   # integração com API pública DataJud (US-20)
│   │   ├── protocol.py            # DataJudClient (Protocol)
│   │   ├── datajud_service.py     # implementação real via httpx
│   │   ├── fake_service.py        # implementação fake para testes
│   │   ├── service.py             # sync manual/lote, dedup e persistência
│   │   ├── deps.py                # get_datajud_client(), get_datajud_service()
│   │   └── router.py              # /processes/{id}/sync, /datajud/sync-active-processes
│   ├── documents/                 # documentos anexados aos processos (US04)
│   │   ├── model.py               # ORM: ProcessDocument
│   │   ├── schema.py              # ProcessDocumentRead
│   │   ├── repository.py
│   │   ├── service.py             # upload, listagem, download e exclusão
│   │   ├── storage.py             # DocumentStorage (Protocol) + LocalDocumentStorage
│   │   ├── deps.py                # get_document_storage(), get_process_document_service()
│   │   └── router.py              # /processes/{id}/documents
│   ├── external_api_logs/         # logs de sucesso/falha de integrações externas
│   │   ├── model.py               # ORM: ExternalApiLog
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   ├── notifier.py            # notifica admins em falhas via notifications
│   │   └── router.py              # GET /external-api-logs (admin)
│   ├── notifications/             # preferências e disparo de notificações por e-mail
│   │   ├── model.py               # ORM: NotificationPreference
│   │   ├── schema.py              # EventType, PreferencesRead, PreferencesUpdate
│   │   ├── repository.py
│   │   ├── service.py             # notify(user_id, event_type, payload)
│   │   ├── deps.py
│   │   ├── router.py              # GET/PATCH /notifications/preferences
│   │   └── templates/             # subject + body por evento
│   ├── forensic_holidays/         # feriados forenses (nacional, court, comarca)
│   │   ├── model.py               # ORM: ForensicHoliday, HolidayScope
│   │   ├── schema.py
│   │   ├── repository.py
│   │   ├── service.py
│   │   ├── deps.py
│   │   ├── router.py              # /forensic-holidays (GET autenticado, CUD admin)
│   │   ├── data/holidays.json     # nacionais + recesso + TJDFT
│   │   └── seed.py                # `python -m app.modules.forensic_holidays.seed`
│   ├── deadlines/                 # cálculo, persistência e alertas de prazos
│   │   ├── model.py               # ORM: Deadline, DeadlineAlert
│   │   ├── schema.py              # DeadlineCalculate*, DeadlineCreate/Update/Read, DeadlineAlertRead
│   │   ├── repository.py          # DeadlineRepository, DeadlineAlertRepository
│   │   ├── service.py             # calculate_due_date, business_days_until, dispatch_alerts
│   │   ├── deps.py
│   │   └── router.py              # /deadlines/calculate, /processes/{id}/deadlines, /deadlines/{id}, .../alerts
│   ├── appointments/              # agenda de compromissos (CRUD pessoal)
│   │   ├── model.py               # ORM: Appointment, AppointmentType
│   │   ├── schema.py              # AppointmentCreate/Update/Read
│   │   ├── repository.py
│   │   ├── service.py             # CRUD + validação de refs + autorização + sync Google
│   │   ├── deps.py
│   │   └── router.py              # /appointments, /appointments/{id}
│   ├── google_calendar/           # integração OAuth + sync com Google Calendar
│   │   ├── model.py               # ORM: GoogleCredential
│   │   ├── schema.py
│   │   ├── repository.py
│   │   ├── crypto.py              # TokenCipher (Fernet) p/ o refresh_token
│   │   ├── protocol.py            # GoogleCalendarClient (Protocol)
│   │   ├── google_service.py      # impl real (Google Calendar API)
│   │   ├── fake_service.py        # impl fake para testes
│   │   ├── oauth.py               # fluxo OAuth (auth URL, troca de code)
│   │   ├── service.py             # GoogleCalendarService + sync_appointment
│   │   ├── deps.py
│   │   └── router.py              # /integrations/google/*
│   ├── processes/                 # processos judiciais (core do domínio)
│   │   ├── model.py               # ORM: Process, ProcessMovement, ProcessNote, ProcessStatus
│   │   ├── schema.py              # ProcessCreate/Read, MovementCreate/Read, ProcessNoteCreate/Update/Read
│   │   ├── repository.py
│   │   ├── service.py             # CRUD + mudança de status + movimentações + notas + notificações
│   │   ├── deps.py
│   │   └── router.py              # /processes, /processes/{id}, .../status, .../movements, .../notes
│   ├── tasks/                     # tarefas em Kanban (CRUD + move atômico)
│   │   ├── model.py               # ORM: Task, TaskStatus, TaskPriority
│   │   ├── schema.py              # TaskCreate, TaskUpdate, TaskMove, TaskRead
│   │   ├── repository.py          # CRUD + reordenação atômica em transação
│   │   ├── service.py             # valida referências, dispara TASK_ASSIGNED
│   │   ├── deps.py
│   │   └── router.py              # /tasks, /tasks/{id}, /tasks/{id}/move
│   └── health/                    # health check
│       ├── schema.py
│       ├── service.py
│       ├── deps.py
│       └── router.py
└── api/
    └── router.py                  # agrega todos os modules/*/router.py
```

```
tests/
├── conftest.py                     # fixture globais e setup de ambiente
├── config/                         # testes de configuração
├── unit/
│   ├── modules/
│   │   ├── users/                 test_user_service.py
│   │   ├── leads/                 test_lead_service.py
│   │   ├── auth/                  test_auth_service.py
│   │   ├── health/                test_health_controller.py
│   │   ├── media/                 test_media_service.py, test_local_storage.py
│   │   ├── office_config/         test_office_config_service.py
│   │   ├── audit_logs/            (testes de auditoria)
│   │   ├── articles/              (testes de artigos)
│   │   ├── clients/               (testes de clientes)
│   │   ├── deadlines/             (testes de prazos)
│   │   ├── appointments/          (testes de compromissos)
│   │   ├── tasks/                 test_task_service.py
│   │   ├── processes/             test_process_service.py, test_schema.py
│   │   ├── notifications/         test_notification_service.py, test_templates.py
│   │   ├── google_calendar/       test_google_calendar_service.py, test_token_cipher.py
│   │   ├── datajud/               (testes de integração DataJud)
│   │   └── forensic_holidays/     (testes de feriados forenses)
│   ├── shared/                    test_responses.py, test_auth_deps.py
│   ├── scheduler/                 test_deadline_alert_config.py
│   └── scripts/                   test_sync_datajud_active_processes.py
├── integration/
│   ├── modules/
│   │   ├── users/                 test_user_repository.py
│   │   ├── leads/                 test_lead_repository.py
│   │   ├── office_config/         test_office_config_repository.py
│   │   ├── tasks/                 test_task_repository.py
│   │   ├── processes/             test_process_repository.py
│   │   ├── clients/               (testes de repositório de clientes)
│   │   ├── appointments/          (testes de repositório de compromissos)
│   │   ├── articles/              (testes de repositório de artigos)
│   │   ├── deadlines/             (testes de repositório de prazos)
│   │   ├── notifications/         (testes de repositório de notificações)
│   │   ├── audit_logs/            (testes de repositório de auditoria)
│   │   ├── google_calendar/       (testes de repositório Google Calendar)
│   │   ├── datajud/               (testes de repositório DataJud)
│   │   └── forensic_holidays/     (testes de repositório de feriados)
└── e2e/
    ├── conftest.py               # fixtures de e2e (cliente HTTP, BD de teste, etc)
    └── modules/
        ├── users/                 test_users.py
        ├── leads/                 test_leads.py
        ├── auth/                  test_auth.py
        ├── health/                test_health.py
        ├── media/                 test_media.py
        ├── office_config/         test_office_config.py
        ├── articles/              test_articles.py
        ├── clients/               test_clients.py
        ├── deadlines/             test_deadlines.py
        ├── appointments/          test_appointments.py
        ├── tasks/                 test_tasks.py
        ├── processes/             test_processes.py
        ├── notifications/         test_notifications.py
        ├── audit_logs/            test_audit_logs.py
        ├── google_calendar/       test_google_calendar.py
        ├── datajud/               test_datajud.py
        └── forensic_holidays/     test_forensic_holidays.py
```

---

## Camadas e responsabilidades

Cada módulo em `modules/` contém as mesmas camadas internas:

### `router.py` — Rotas (entrada HTTP)

Ponto de entrada de cada requisição. Define os endpoints, valida entrada via schemas Pydantic, injeta dependências via `Depends` e chama o service diretamente. Não contém lógica de negócio.

**Fronteira de serialização:** o router é o único ponto onde ORM é convertido para schema Pydantic. Services sempre retornam ORM; o router chama `ModelRead.model_validate(orm_obj)` explicitamente antes de passar para `ok()` ou `paginated()`:

```python
# correto
return ok(UserRead.model_validate(service.get_user(user_id)))
return paginated([UserRead.model_validate(u) for u in items], total, page, limit)

# errado — service não deve retornar Pydantic
return ok(service.get_user(user_id))
```

Exceções justificadas (transformações que não são mapeamento 1-para-1 de ORM):

- `articles` — `_to_read()` agrega campos de relações joined
- `clients.timeline_service` — monta feed heterogêneo de múltiplos tipos de evento
- `datajud` — `DataJudSyncResponse` é sumário de operação de sync, não mapeamento de entidade

### `deps.py` — Fábrica de dependências

Expõe funções `get_X_service()` que constroem o grafo de dependências (repositories → services) e são registradas no FastAPI via `Depends`. É o único lugar do módulo que conhece quais repositories o service precisa.

### `service.py` — Regras de negócio

Concentra a lógica do domínio: validações de negócio, cálculos, decisões. Usa o repository para persistência. É a camada mais importante e deve ter maior cobertura de testes.

### `repository.py` — Acesso a dados

Responsável exclusivamente por interagir com o banco: queries, inserções, atualizações e deleções. Recebe e retorna models ORM. Não conhece regras de negócio. Nunca chama `db.commit()` — a transação é fechada pelo service via `unit_of_work`.

### `model.py` — Modelo ORM

Define o esquema do banco de dados via SQLAlchemy. Representa a entidade persistida. Herda de `shared/base_model.py`.

### `schema.py` — Contratos de entrada e saída

Schemas Pydantic que definem o formato esperado nas requisições e nas respostas. Funcionam como DTOs e desacoplam a camada HTTP dos models internos.

---

## `shared/` — Código transversal

Código que pertence a nenhum módulo específico, mas é usado por vários, organizado por camada:

### `shared/db/`

- **`base_model.py`** — `DeclarativeBase` do SQLAlchemy; todos os models herdam daqui
- **`uow.py`** — `unit_of_work` para abrir e fechar transações

### `shared/deps/`

- **`auth.py`** — `get_current_user()` e `require_admin()`; dependências de autenticação injetadas via `Depends()` nas rotas
- **`email.py`** — injeção de `EmailService` (real ou fake)
- **`google.py`** — injeção de `GoogleCalendarClient` (real ou fake)

### `shared/http/`

- **`responses.py`** — `SuccessResponse[T]`, `PaginatedResponse[T]`, `ErrorResponse`; helpers `ok()`, `paginated()`, `error_responses()`

### `shared/service/`

- **`helpers.py`** — funções utilitárias compartilhadas entre services

### `shared/` (raiz)

- **`exceptions.py`** — `AppException` e subclasses; lançadas nos services, convertidas pelo handler global
- **`datajud.py`** — utilitários para integração com DataJud
- **`types.py`** — tipos customizados e type aliases

---

## Fluxo de uma requisição

```
HTTP Request
  └─► modules/*/router.py              valida entrada com schema
        │  Depends(get_X_service)       deps.py constrói o grafo
        └─► modules/*/service.py        aplica regras de negócio
              └─► modules/*/repository  executa query no banco
                    └─► modules/*/model entidade ORM
  ◄── HTTP Response
        schema serializa a saída
```

---

## Padrão de resposta

Definido em `app/shared/responses.py`. Três tipos de envelope:

### Sucesso simples — `SuccessResponse[T]`

```json
{ "success": true, "data": { ... } }
```

Usar o helper `ok(data)` nas rotas.

### Sucesso paginado — `PaginatedResponse[T]`

```json
{
  "success": true,
  "data": [ ... ],
  "meta": { "total": 100, "page": 1, "limit": 10, "pages": 10 }
}
```

Usar o helper `paginated(items, total, page, limit)` nas rotas.

### Erro — `ErrorResponse`

```json
{ "success": false, "error": { "code": "ERROR_CODE", "message": "mensagem legível" } }
```

Erros de negócio devem ser lançados como subclasses de `AppException` (definidas em `app/shared/exceptions.py`). O handler global converte para `ErrorResponse` automaticamente. Nunca usar `HTTPException` diretamente nos services.

Erros disponíveis:

| Classe                    | HTTP | `code`                 |
| ------------------------- | ---- | ---------------------- |
| `InvalidCredentialsError` | 401  | `INVALID_CREDENTIALS`  |
| `InactiveUserError`       | 403  | `INACTIVE_USER`        |
| `UnauthorizedError`       | 401  | `UNAUTHORIZED`         |
| `ForbiddenError`          | 403  | `FORBIDDEN`            |
| `UserNotFoundError`       | 404  | `USER_NOT_FOUND`       |
| `EmailAlreadyExistsError` | 409  | `EMAIL_ALREADY_EXISTS` |

Para documentar respostas de erro no Swagger, usar o helper `error_responses(*codes)`:

```python
@router.get("/exemplo", responses=error_responses(401, 403, 404))
```

---

## Injeção de dependência

O projeto usa o sistema nativo de DI do FastAPI via `Depends`. O padrão é:

```
deps.py (módulo)      →  get_X_service() constrói o grafo (Repository → Service)
shared/deps/*.py      →  get_current_user(), require_admin(), get_email_service(), get_google_client()
router.py (módulo)    →  injeta o service via Depends(get_X_service)
service.py (módulo)   →  recebe dependências já construídas no __init__
repository.py (módulo) →  único ponto que recebe Session
```

### Dependências centralizadas em `shared/deps/`

- **`auth.py`** — autenticação e autorização
- **`email.py`** — injeção de EmailService (real ou fake)
- **`google.py`** — injeção de GoogleCalendarClient (real ou fake)

### `deps.py` — construção do grafo por módulo

Cada módulo tem um `deps.py` com funções que montam o service com suas dependências e são registradas no FastAPI via `Depends`. Dependências compartilhadas (como `EmailService`, autenticação) vêm de `shared/deps/`:

```python
# users/deps.py
from app.shared.deps.email import get_email_service
from app.shared.deps.auth import get_current_user

def get_user_service(
    db: Session = Depends(get_db),
    email: EmailService = Depends(get_email_service),
) -> UserService:
    return UserService(
        UserRepository(db),
        email,
        AuditLogService(AuditLogRepository(db)),
    )
```

### `router.py` — injeção via Depends

O router injeta o service como parâmetro da rota — FastAPI resolve o grafo automaticamente. Dependências compartilhadas são importadas de `shared.deps`:

```python
# users/router.py
from app.shared.deps.auth import get_current_user, require_admin

def create_user(
    payload: UserCreate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(require_admin),
) -> SuccessResponse[UserRead]:
    return ok(UserRead.model_validate(service.create_user(payload, created_by=current_user)))
```

### `service.py` — recebe dependências prontas

Service recebe repositórios e serviços já construídos, nunca recebe `Session`:

```python
class UserService:
    def __init__(self, repository: UserRepository, email: EmailService, audit: AuditLogService) -> None:
        self.repository = repository
        self.email = email
        self.audit = audit
```

### `repository.py` — único ponto que recebe Session

```python
class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db
```

### Módulos sem banco de dados

Módulos sem persistência (ex: `media`) não recebem `db`. O `deps.py` instancia o provider padrão diretamente:

```python
# media/deps.py
def get_media_service() -> MediaService:
    return MediaService(LocalStorageProvider())
```

Para testes que precisam de um provider alternativo, usar `app.dependency_overrides`:

```python
app.dependency_overrides[get_media_service] = lambda: MediaService(FakeStorageProvider())
```

### O que não fazer

- **Service receber `Session` diretamente** — quem constrói repositories é o `deps.py`, não o service
- **Router instanciar repositories ou services diretamente** — responsabilidade do `deps.py`
- **`deps.py` conter lógica de negócio** — apenas constrói e injeta; lógica vai no service

---

## Testes

O projeto organiza testes em três níveis:

### Unit — `tests/unit/`

Testes isolados de unidades (services, repositories, controllers). Usam **mocks** e **fakes** para dependências externas.

**Scope:**

- `service.py` — lógica de negócio; maior cobertura esperada
- `model.py`, `schema.py` — validação de dados
- `helpers.py` e `shared/` — utilitários

**Exemplo:**

```python
# tests/unit/modules/users/test_user_service.py
from unittest.mock import Mock
from app.modules.users.service import UserService

def test_create_user_success():
    repo = Mock()
    repo.get_by_email.return_value = None

    service = UserService(repo)
    result = service.create_user(UserCreate(email="test@example.com", password="..."))

    assert result.email == "test@example.com"
    repo.get_by_email.assert_called_once()
```

### Integration — `tests/integration/`

Testes de **repository** contra banco de dados real (SQLite em memória). Validam queries e persistência.

**Scope:**

- `repository.py` — queries SQL, transações, constraints

**Setup:** usa `conftest.py` com fixture `db` (Session com banco de teste)

**Exemplo:**

```python
# tests/integration/modules/users/test_user_repository.py
def test_user_repository_create(db: Session):
    repo = UserRepository(db)
    user = repo.create(User(email="test@example.com"))

    fetched = repo.get_by_id(user.id)
    assert fetched.email == "test@example.com"
```

### E2E — `tests/e2e/`

Testes de fluxos completos via **cliente HTTP** contra aplicação real.

**Scope:**

- Rotas (`router.py`) com todas as camadas (auth, service, repository, DB)
- Validação de schemas Pydantic e serialização
- Autenticação e autorização

**Setup:**

- Fixture `client` (TestClient do FastAPI)
- Banco de teste limpo antes de cada teste (`conftest.py` com `app.dependency_overrides`)

**Exemplo:**

```python
# tests/e2e/modules/users/test_users.py
def test_create_user_e2e(client: TestClient, admin_token: str):
    response = client.post(
        "/api/v1/users",
        json={"email": "test@example.com", "password": "..."},
        headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 201
    assert response.json()["data"]["email"] == "test@example.com"
```

### `conftest.py` — Fixtures globais

- `tests/conftest.py` — variáveis de ambiente, setup global
- `tests/e2e/conftest.py` — cliente HTTP, aplicação com dependências overrideadas, BD de teste

### Executar testes

```bash
# Todos os testes
pytest

# Apenas unit
pytest tests/unit/

# Apenas integration
pytest tests/integration/

# Apenas e2e
pytest tests/e2e/

# Um módulo específico
pytest tests/unit/modules/users/

# Com cobertura HTML
pytest --cov=app --cov-report=html
# Abre em: htmlcov/index.html

# Verboso + saída detalhada
pytest -vv -s

# Parar no primeiro erro
pytest -x

# Apenas testes que passaram antes (usar depois de correção)
pytest --lf
```

---

## Adicionando um novo módulo

Para cada nova história de usuário que introduz um novo domínio (ex: `contracts`):

1. **Criar pasta** `app/modules/contracts/`
2. **Criar arquivos de domínio:** `model.py`, `schema.py`, `repository.py`, `service.py`, `deps.py`, `router.py`
3. **Registrar router** em `app/api/router.py`
4. **Criar testes** em três níveis:
   - `tests/unit/modules/contracts/` — testes do service (lógica de negócio)
   - `tests/integration/modules/contracts/` — testes do repository (BD)
   - `tests/e2e/modules/contracts/` — testes de fluxo HTTP (rotas)
5. **Garantir cobertura mínima** de testes (verificar com `pytest --cov`)

Zero toque em código de outros módulos.

---

## Princípios que guiam as decisões

- **Módulo autônomo:** cada módulo contém todas as suas camadas; mudança em um módulo não toca outros.
- **Regras de negócio no service:** nenhuma lógica de domínio nas rotas, deps ou repositories.
- **Schemas desacoplados dos models:** nunca expor diretamente um model ORM na resposta da API. Services retornam ORM; routers serializam via `ModelRead.model_validate()` explícito.
- **Repository como única porta para o banco:** nenhuma query fora do repository.
- **Repository nunca comita:** transações são abertas e fechadas pelo service via `with unit_of_work(db):`.
- **Dependências entre módulos apenas quando semânticas e unidirecionais:** evitar acoplamento arbitrário entre módulos. Dependências circulares são proibidas. Dependências com relação de domínio clara são permitidas (ex: `auth` depende de `users` porque autentica usuários, já o inverso não existe).
- **Erros via exceções customizadas:** toda falha de negócio deve ser lançada como subclasse de `AppException`; nunca usar `HTTPException` diretamente nos services.
- **Versionamento de rotas:** toda rota pública fica sob `/api/v1/` para permitir evolução sem quebrar contratos.

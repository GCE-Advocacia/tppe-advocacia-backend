# US09 — Documentos no Google Drive: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** guardar os documentos dos processos no Google Drive do escritório (uma pasta por número de processo), com conexão OAuth feita pelo administrador na página de Processos.

**Architecture:** um módulo novo `app/modules/google_drive` cuida da conexão única do escritório (OAuth `drive.file`, refresh token criptografado), do cliente da API do Drive (real e fake) e do registro de falhas. Um `DriveDocumentStorage` entra ao lado do `LocalDocumentStorage`, atrás do mesmo `DocumentStorage`. Cada documento registra em que storage está. O frontend ganha um bloco de conexão na página de Processos e mensagens para os novos códigos de erro.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, `google-api-python-client` e `google-auth-oauthlib` (já são dependências), pytest. React + TypeScript (Vite), testes `node:test` + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-27-us09-google-drive-design.md`

## Global Constraints

- Escopo OAuth: exatamente `https://www.googleapis.com/auth/drive.file`.
- Uma única conexão para o escritório inteiro. Só administrador conecta e desconecta.
- Nome da pasta raiz: `Sistema Advocacia — Documentos`. Pasta do processo: `format_cnj(process.number)` (de `app/modules/processes/schema.py`).
- Nenhum arquivo recebe permissão nova nem link público. O download sempre passa pelo backend.
- Excluir manda o arquivo para a **lixeira** do Drive (`trashed=True`), nunca apaga definitivamente.
- Drive não conectado: HTTP 409, código `GOOGLE_DRIVE_NOT_CONNECTED`. Falha do Google: HTTP 503, código `GOOGLE_DRIVE_UNAVAILABLE`.
- Logs de falha: provider `GOOGLE_DRIVE`; operações `DOCUMENT_UPLOAD`, `DOCUMENT_DOWNLOAD`, `DOCUMENT_DELETE`, `OAUTH`. Sucessos não são registrados.
- `DOCUMENT_STORAGE` aceita `local` (padrão) ou `drive`. Com `APP_ENV=production`, qualquer valor diferente de `drive` impede a API de subir.
- Callback do Drive: `GOOGLE_DRIVE_REDIRECT_URI`, rota `/api/v1/integrations/google-drive/callback`. Ele redireciona para `{FRONTEND_URL}/sistema/processos?google_drive=connected|error`.
- Os testes nunca chamam o Google de verdade.
- Commits: terminar com `Co-authored-by: Isa Costa <iisabellecostaf@gmail.com>` e `Co-authored-by: Vitor Pereira Bessa <Bessa.vitor06@gmail.com>`, sem atribuição do Claude. Branches saem da `main` (`feature/us09-google-drive` nos dois repositórios).
- Testes do backend: rodar com Python 3.11 (os testes usam `datetime.UTC`). As 2 falhas de `tests/integration/modules/payments/test_payment_reminder_service.py` já existem na `main` e não fazem parte deste trabalho.

## Review Focus

1. **Pasta apagada no Drive pelo escritório** (raiz ou do processo, inclusive se estiver só na lixeira): o próximo upload recria a pasta e atualiza o ID guardado, em vez de falhar. *Testes nas Tasks 4 e 6.*
2. **Refresh token revogado** (o usuário removeu o app da conta Google): o sistema apaga a conexão, registra a falha e responde 409 `GOOGLE_DRIVE_NOT_CONNECTED`, e não 503. *Teste na Task 3.*
3. **Documento antigo `storage=local` com `DOCUMENT_STORAGE=drive`**: download e exclusão continuam usando o disco. *Teste na Task 6.*
4. **Nome de arquivo com acento ou espaço no download**: o cabeçalho `Content-Disposition` usa `filename*=UTF-8''...` e o navegador recebe o nome original. *Teste na Task 6.*
5. **`state` do Calendar reutilizado no callback do Drive**, ou `state` de um usuário que não é admin: o callback recusa e redireciona com `google_drive=error`, sem gravar conexão. *Teste na Task 5.*

---

### Task 1: Configuração, exceções e enums de log

**Files:**
- Modify: `app/config/settings.py`
- Modify: `app/shared/exceptions.py`
- Modify: `app/modules/external_api_logs/model.py`
- Modify: `.env.example`
- Test: `tests/unit/config/test_settings.py`

**Interfaces:**
- Produces:
  - `Settings.document_storage: Literal["local", "drive"]` (env `DOCUMENT_STORAGE`, padrão `"local"`, `validate_default=True`);
  - `Settings.google_drive_redirect_uri: str` (env `GOOGLE_DRIVE_REDIRECT_URI`, padrão `"http://localhost:8000/api/v1/integrations/google-drive/callback"`);
  - `Settings.google_drive_configured: bool` (property: `google_client_id`, `google_client_secret`, `google_token_encryption_key` e `google_drive_redirect_uri` preenchidos);
  - exceções `GoogleDriveNotConnectedError()` (409, `GOOGLE_DRIVE_NOT_CONNECTED`, "Google Drive is not connected"), `GoogleDriveUnavailableError()` (503, `GOOGLE_DRIVE_UNAVAILABLE`, "Google Drive is unavailable") e `GoogleDriveNotConfiguredError()` (503, `GOOGLE_DRIVE_NOT_CONFIGURED`, "Google Drive integration is not configured on the server");
  - `ExternalApiProvider.GOOGLE_DRIVE`; `ExternalApiOperation.DOCUMENT_UPLOAD`, `DOCUMENT_DOWNLOAD`, `DOCUMENT_DELETE` e `OAUTH`.

- [ ] **Step 1: Write the failing tests** em `TestDocumentStorageValidator`:
  - `test_defaults_to_local_outside_production`: `Settings(_env_file=None).document_storage == "local"`;
  - `test_requires_drive_in_production`: com `APP_ENV=production`, `MEDIA_BUCKET=uploads` e sem `DOCUMENT_STORAGE`, ocorre `ValidationError` contendo `"DOCUMENT_STORAGE"`;
  - `test_accepts_drive_in_production`: com `DOCUMENT_STORAGE=drive`, sem erro.

  Atualize `test_accepts_strong_secret_in_production` para também definir `DOCUMENT_STORAGE=drive`.
- [ ] **Step 2: Run** `python -m pytest tests/unit/config/test_settings.py -v`. Esperado: os 3 testes novos falham.
- [ ] **Step 3: Implement** os campos, o validator (no mesmo estilo de `object_storage_in_production`), as exceções e os valores de enum. As colunas usam `native_enum=False` sem `CHECK`, então não precisa de migração. Acrescente `DOCUMENT_STORAGE=local` e `GOOGLE_DRIVE_REDIRECT_URI=...` no `.env.example`, com um comentário de uma linha.
- [ ] **Step 4: Run** o mesmo comando. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: configuração e erros do Google Drive (US09)`.

### Task 2: Modelos, migração e repositórios

**Files:**
- Create: `app/modules/google_drive/__init__.py`, `app/modules/google_drive/model.py`, `app/modules/google_drive/repository.py`
- Modify: `app/modules/documents/model.py` (coluna `storage`)
- Modify: `alembic/env.py` (import dos novos modelos, como os outros)
- Create: `alembic/versions/20261027_add_google_drive.py` (`down_revision = "7d8e9f0a1b2c"`)
- Test: `tests/integration/modules/google_drive/test_google_drive_repository.py`

**Interfaces:**
- Produces:
  - Modelo `GoogleDriveConnection` (tabela `google_drive_connection`): `id` int PK; `encrypted_refresh_token` Text not null; `email` String(255) null; `root_folder_id` String(128) null; `connected_by` FK `users.id` `ondelete=SET NULL`, null; `connected_at` timestamptz `server_default=now()`.
  - Modelo `ProcessDriveFolder` (tabela `process_drive_folders`): `id`; `process_id` FK `processes.id` `ondelete=CASCADE`, unique; `folder_id` String(128) not null.
  - `ProcessDocument.storage: Mapped[str]`, String(10), not null, `server_default="local"`.
  - `GoogleDriveConnectionRepository(db)`:
    - `get() -> GoogleDriveConnection | None`;
    - `save(encrypted_refresh_token: str, email: str | None, connected_by: int) -> GoogleDriveConnection` (substitui a linha existente e zera `root_folder_id`);
    - `set_root_folder(folder_id: str) -> None`;
    - `delete() -> None`.
  - `ProcessDriveFolderRepository(db)`: `get_folder_id(process_id: int) -> str | None` e `set_folder_id(process_id: int, folder_id: str) -> None` (upsert).
  - Os repositórios só fazem `add`/`flush`. Quem comita é o service, via `unit_of_work`.

- [ ] **Step 1: Write the failing tests** (SQLite em memória, como em `tests/integration/modules/office_config/test_office_config_logo_api.py`, criando só as tabelas necessárias):
  - `test_save_replaces_previous_connection_and_clears_root`: dois `save` resultam em 1 linha, com `root_folder_id is None` e os dados do último;
  - `test_delete_removes_connection`;
  - `test_folder_upsert`: `set_folder_id(1, "a")` e depois `set_folder_id(1, "b")` resultam em `get_folder_id(1) == "b"`;
  - `test_document_storage_defaults_to_local`.
- [ ] **Step 2: Run** `python -m pytest tests/integration/modules/google_drive -v`. Esperado: FAIL de import.
- [ ] **Step 3: Implement** os modelos, os repositórios e a migração (`create_table` × 2 e `add_column` com `server_default="local"`; o downgrade desfaz).
- [ ] **Step 4: Run** os testes. Esperado: PASS. Depois rode `alembic upgrade head` contra um Postgres local (`docker compose up db`) e confirme que aplica sem erro.
- [ ] **Step 5: Commit** `feat: tabelas da conexão e pastas do Google Drive (US09)`.

### Task 3: Cliente do Drive (real e fake) e tradução de erros

**Files:**
- Create: `app/modules/google_drive/client.py`, `app/modules/google_drive/fake_client.py`
- Test: `tests/unit/modules/google_drive/test_drive_client.py`

**Interfaces:**
- Produces:
  - `class DriveClient(Protocol)`, com os métodos:
    - `create_folder(name: str, parent_id: str | None) -> str`;
    - `folder_exists(folder_id: str) -> bool` (False se não existe ou se `trashed`);
    - `upload_file(name: str, content: bytes, mime_type: str, parent_id: str) -> str`;
    - `download_file(file_id: str) -> bytes`;
    - `trash_file(file_id: str) -> None`;
    - `get_email() -> str | None`.
  - Erros do próprio módulo (não são `AppException`): `DriveAuthRevokedError` (refresh token inválido, `google.auth.exceptions.RefreshError`), `DriveNotFoundError` (HTTP 404) e `DriveApiError(http_status: int | None, message: str)` (qualquer outro erro, incluindo timeout).
  - `GoogleDriveApiClient(refresh_token: str, settings: Settings)` implementa `DriveClient` com `googleapiclient.discovery.build("drive", "v3", credentials=..., cache_discovery=False)` e escopo `drive.file`. Toda chamada passa por um único método que converte as exceções do Google nos três erros acima.
  - `revoke_refresh_token(refresh_token: str) -> None`: POST em `https://oauth2.googleapis.com/revoke` com `httpx`, engolindo qualquer erro.
  - `FakeDriveClient` (em memória): guarda `folders: dict[id, (name, parent)]`, `files: dict[id, (name, bytes, mime, parent)]` e `trashed: set[id]`. Tem os atributos `raise_on_next: Exception | None` (lançado e zerado na próxima chamada) e `email = "escritorio@example.test"`.

- [ ] **Step 1: Write the failing tests** com o cliente real e `googleapiclient.http.HttpMockSequence`, sem rede:
  - `test_http_404_becomes_not_found`;
  - `test_http_500_becomes_api_error_with_status`;
  - `test_refresh_error_becomes_auth_revoked` (monkeypatch das credentials para lançar `RefreshError`);
  - `test_upload_sends_parent_and_no_permissions`: confere no corpo enviado que vão `parents=[parent_id]` e `name`, e que não há chamada a `permissions`.

  Com o fake:
  - `test_fake_trash_hides_folder_from_folder_exists`;
  - `test_fake_raise_on_next`.
- [ ] **Step 2: Run** `python -m pytest tests/unit/modules/google_drive/test_drive_client.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implement** os dois clientes. Upload com `MediaIoBaseUpload(BytesIO(content), mimetype=..., resumable=False)` e `fields="id"`. Download com `files().get_media` + `MediaIoBaseDownload`. Lixeira com `files().update(fileId, body={"trashed": True})`. `folder_exists` com `files().get(fields="id,trashed")`. `get_email` com `about().get(fields="user(emailAddress)")`.
- [ ] **Step 4: Run** os testes. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: cliente da API do Google Drive (US09)`.

### Task 4: `GoogleDriveService` (conexão, OAuth e falhas)

**Files:**
- Modify: `app/modules/google_calendar/oauth.py` (`GoogleOAuthFlow` passa a receber escopos e redirect)
- Create: `app/modules/google_drive/service.py`, `app/modules/google_drive/schema.py`
- Test: `tests/unit/modules/google_drive/test_google_drive_service.py`

**Interfaces:**
- Consumes: repositórios da Task 2; `DriveClient` e os erros da Task 3; `TokenCipher` (`app/modules/google_calendar/crypto.py`); `ExternalApiLogRepository.create(...)` e `ExternalApiFailureNotifier.notify_failure(log)`.
- Produces:
  - `GoogleOAuthFlow(settings, scopes: list[str] = SCOPES, redirect_uri: str | None = None)`, sem mudar o comportamento atual do Calendar. `exchange_code` continua retornando `(refresh_token, scope)`.
  - `GoogleDriveStatusRead(connected: bool, email: str | None)` e `GoogleDriveAuthUrlRead(auth_url: str)`.
  - `GoogleDriveService`, com o construtor `(connections: GoogleDriveConnectionRepository, folders: ProcessDriveFolderRepository, users: UserRepository, log_repository: ExternalApiLogRepository, notifier: ExternalApiFailureNotifier | None, oauth: GoogleOAuthFlow | None, cipher: TokenCipher | None, state_secret: str, client_factory: Callable[[str], DriveClient])` e os métodos:
    - `get_status() -> GoogleDriveStatusRead`;
    - `build_auth_url(user_id: int) -> str`: levanta `GoogleDriveNotConfiguredError` se `oauth`/`cipher` forem `None`; o `state` é um JWT com `purpose="google_drive"` e TTL de 10 minutos;
    - `handle_callback(code: str, state: str) -> None`: valida o `state` e se o `sub` é um admin ativo; troca o code; lê o e-mail com `client_factory(refresh_token).get_email()`; salva a conexão. Qualquer falha levanta `GoogleOAuthError` (de `google_calendar.service`) e registra falha `OAUTH`;
    - `disconnect() -> None`: chama `revoke_refresh_token` e apaga a conexão;
    - `client() -> DriveClient`: levanta `GoogleDriveNotConnectedError` sem conexão;
    - `root_folder_id(client: DriveClient) -> str` e `process_folder_id(client: DriveClient, process_id: int, process_number: str) -> str`: verificam com `folder_exists`, criam se faltar e gravam o ID;
    - `fail(operation: ExternalApiOperation, exc: Exception, user_id: int | None, process_id: int | None = None) -> NoReturn`: grava o log numa transação própria e chama o notifier. Se for `DriveAuthRevokedError`, apaga a conexão e levanta `GoogleDriveNotConnectedError`; senão, levanta `GoogleDriveUnavailableError`.
  - `build_google_drive_service(db: Session, client_factory: Callable[[str], DriveClient] | None = None) -> GoogleDriveService` monta a partir das settings (padrão: `GoogleDriveApiClient`).

- [ ] **Step 1: Write the failing tests** com `FakeDriveClient`, repositórios em SQLite e `MagicMock` para `oauth`/notifier:
  - `test_status_disconnected_then_connected_with_email`;
  - `test_auth_url_requires_configuration`;
  - `test_callback_rejects_calendar_state_and_non_admin` (Review Focus 5): nada gravado, `GoogleOAuthError`;
  - `test_callback_saves_encrypted_token_and_email`: o token salvo é diferente do token puro, e `cipher.decrypt` devolve o original;
  - `test_root_and_process_folders_are_created_once_then_reused`: o nome da pasta do processo é `format_cnj("00012345620248260100")`;
  - `test_missing_or_trashed_folder_is_recreated_and_saved` (Review Focus 1);
  - `test_fail_with_revoked_token_disconnects_and_raises_not_connected` (Review Focus 2): a conexão some, o log `GOOGLE_DRIVE`/`DOCUMENT_UPLOAD`/`FAILURE` existe e o notifier foi chamado;
  - `test_fail_with_api_error_raises_unavailable_and_keeps_connection`;
  - `test_disconnect_revokes_and_deletes` (com `revoke_refresh_token` em monkeypatch).
- [ ] **Step 2: Run** `python -m pytest tests/unit/modules/google_drive/test_google_drive_service.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implement** o service e o ajuste no `GoogleOAuthFlow`. O `state` segue o padrão de `GoogleCalendarService._encode_state`/`_decode_state`, com o propósito próprio do Drive.
- [ ] **Step 4: Run** estes testes e também `tests/unit/modules/google_calendar`. Esperado: PASS, com o Calendar intacto.
- [ ] **Step 5: Commit** `feat: conexão do escritório com o Google Drive (US09)`.

### Task 5: Endpoints `/integrations/google-drive`

**Files:**
- Create: `app/modules/google_drive/router.py`, `app/modules/google_drive/deps.py`
- Modify: `app/api/router.py` (incluir o router)
- Test: `tests/integration/modules/google_drive/test_google_drive_api.py`

**Interfaces:**
- Consumes: `GoogleDriveService` e `build_google_drive_service` (Task 4); `get_current_user`, `require_admin`.
- Produces:
  - `get_drive_client_factory() -> Callable[[str], DriveClient]`, a dependência que os testes sobrescrevem com uma fábrica do `FakeDriveClient`;
  - `get_google_drive_service(db, client_factory) -> GoogleDriveService`;
  - as rotas:
    - `GET /integrations/google-drive/status` (qualquer usuário logado) → `SuccessResponse[GoogleDriveStatusRead]`;
    - `GET /integrations/google-drive/auth-url` (`require_admin`) → `SuccessResponse[GoogleDriveAuthUrlRead]`;
    - `GET /integrations/google-drive/callback` (sem auth) → 302 para `{frontend_url}/sistema/processos?google_drive=connected` ou `=error`;
    - `DELETE /integrations/google-drive` (`require_admin`) → 204.

- [ ] **Step 1: Write the failing tests** com `TestClient` e `FakeDriveClient`, seguindo o estilo de `tests/e2e/conftest.py` para os headers de admin e de usuário:
  - `test_status_visible_to_any_user`;
  - `test_auth_url_and_disconnect_forbidden_for_non_admin` (403);
  - `test_callback_with_error_param_redirects_with_error`;
  - `test_callback_success_redirects_to_processos_and_status_connected`, com `GoogleOAuthFlow.exchange_code` em monkeypatch;
  - `test_disconnect_then_status_disconnected`.
- [ ] **Step 2: Run** `python -m pytest tests/integration/modules/google_drive/test_google_drive_api.py -v`. Esperado: FAIL.
- [ ] **Step 3: Implement** router e deps, seguindo `app/modules/google_calendar/router.py`.
- [ ] **Step 4: Run** os testes. Esperado: PASS.
- [ ] **Step 5: Commit** `feat: endpoints de conexão do Google Drive (US09)`.

### Task 6: Documentos no Drive

**Files:**
- Modify: `app/modules/documents/storage.py`, `app/modules/documents/service.py`, `app/modules/documents/deps.py`, `app/modules/documents/router.py`
- Create: `app/modules/documents/drive_storage.py`
- Test: `tests/unit/modules/documents/test_drive_storage.py`, `tests/integration/modules/documents/test_documents_drive_api.py`. Os testes existentes de documentos devem continuar passando, ajustados só para as novas assinaturas.

**Interfaces:**
- Consumes: `GoogleDriveService` (`client`, `root_folder_id`, `process_folder_id`, `fail`) e `get_google_drive_service` (Task 5).
- Produces:
  - `StoredFile` ganha o campo `storage: str`.
  - `DocumentStorage` (Protocol) passa a ter:
    - `name: str` (`"local"` ou `"drive"`);
    - `save(file: UploadFile, process_id: int, process_number: str, original_name: str, user_id: int) -> StoredFile`;
    - `read(stored_name: str) -> bytes`;
    - `delete(stored_name: str, user_id: int | None = None) -> None`.
  - `LocalDocumentStorage` se adapta: `read` substitui `path_for` e os parâmetros novos são ignorados.
  - `DriveDocumentStorage(drive: GoogleDriveService, max_size_mb, allowed_mime_types)`:
    - faz a mesma validação de tamanho e tipo do local (extraia a leitura e validação para uma função compartilhada `read_validated(file, max_size_mb, allowed) -> tuple[bytes, mime, extension]` em `storage.py`);
    - envia com o nome `original_name`;
    - devolve o ID do arquivo do Drive como `stored_name`;
    - qualquer erro da Task 3 vai para `drive.fail(...)` com a operação correspondente.
  - `ProcessDocumentService(repository, process_repository, storages: Mapping[str, DocumentStorage], active: str)`:
    - o upload usa `storages[active]` e grava `document.storage = stored.storage`;
    - o download e a exclusão usam `storages[document.storage]`;
    - `get_download` retorna `tuple[ProcessDocument, bytes]`;
    - na exclusão, depois do commit, `GoogleDriveNotConnectedError` e `GoogleDriveUnavailableError` vindos do storage são engolidos (a falha já foi registrada).
  - `get_document_storages()` monta `{"local": LocalDocumentStorage(...), "drive": DriveDocumentStorage(...)}`. O Drive é criado sem tocar a rede.
  - O download do router responde com `Response(content, media_type=document.mime_type)` e `Content-Disposition: attachment; filename*=UTF-8''{quote(original_name)}`.

- [ ] **Step 1: Write the failing tests:**
  - Unit (com `FakeDriveClient` e `GoogleDriveService` real em SQLite):
    - `test_upload_goes_to_process_folder_with_original_name`;
    - `test_upload_rejects_invalid_type_before_calling_drive`;
    - `test_drive_error_on_upload_is_logged_and_raises_unavailable`;
    - `test_read_and_trash_by_file_id`.
  - Integração via API (`DOCUMENT_STORAGE=drive`, dependências sobrescritas):
    - `test_upload_without_connection_returns_409_not_connected`;
    - `test_upload_list_download_delete_roundtrip`: o arquivo fica em `fake.files` dentro da pasta `format_cnj(number)`, e depois do delete o ID está em `fake.trashed`;
    - `test_db_failure_after_upload_trashes_drive_file`;
    - `test_delete_still_succeeds_when_drive_fails_and_failure_is_logged`;
    - `test_local_document_still_downloads_and_deletes_with_drive_active` (Review Focus 3);
    - `test_download_header_keeps_accented_name`, com `Petição inicial.pdf` resultando em `filename*=UTF-8''Peti%C3%A7%C3%A3o%20inicial.pdf` (Review Focus 4);
    - `test_non_author_non_admin_cannot_delete` (403, como hoje).
- [ ] **Step 2: Run** `python -m pytest tests/unit/modules/documents tests/integration/modules/documents -v`. Esperado: os testes novos falham.
- [ ] **Step 3: Implement** as mudanças acima.
- [ ] **Step 4: Run** a suíte inteira: `python -m pytest -q`. Esperado: tudo passa, exceto as 2 falhas antigas de payments. Rode também `ruff check` e `ruff format --check` nos arquivos alterados.
- [ ] **Step 5: Commit** `feat: documentos dos processos no Google Drive (US09)`, abrir o PR do backend para a `main` e incluir na descrição os passos de implantação da spec.

### Task 7: Frontend — conexão e mensagens de erro

Repositório: `tppe-advocacia-frontend`, branch `feature/us09-google-drive` a partir da `main`.

**Files:**
- Create: `src/services/googleDrive.ts`, `src/pages/sistema/Processos/GoogleDriveConnection.tsx` (estilos em `Processos.module.css`)
- Modify: `src/pages/sistema/Processos/Processos.tsx` (renderiza o bloco no `pageHeader` só para admin e estende `errorMessage`)
- Test: `tests/frontend/google-drive-ui.test.mjs`

**Interfaces:**
- Consumes: as rotas da Task 5 e os códigos de erro da Task 1.
- Produces:
  - em `googleDrive.ts`: `type GoogleDriveStatus = { connected: boolean; email: string | null }`, `getGoogleDriveStatus()`, `getGoogleDriveAuthUrl(): Promise<string>` e `disconnectGoogleDrive(): Promise<void>`, no mesmo estilo de `src/services/googleCalendar.ts`;
  - o componente `GoogleDriveConnection({ onMessage }: { onMessage: (m: { message: string; kind: 'success' | 'error' }) => void })`.
- Textos fixos:
  - desconectado: botão **Conectar Google Drive**;
  - conectado: `Google Drive conectado: {email}` e botão **Desconectar**;
  - retorno `?google_drive=connected`: "Google Drive conectado com sucesso!";
  - retorno `?google_drive=error`: "Não foi possível conectar o Google Drive.";
  - em `errorMessage`, `GOOGLE_DRIVE_NOT_CONNECTED`: para admin, "Conecte o Google Drive para anexar documentos."; para os demais, "O Google Drive não está conectado. Peça a um administrador para conectar.";
  - em `errorMessage`, `GOOGLE_DRIVE_UNAVAILABLE`: "Não foi possível acessar o Google Drive. Tente novamente.".
- O parâmetro `google_drive` é lido com `useSearchParams` e removido depois de mostrar a mensagem.

- [ ] **Step 1: Write the failing tests** em `tests/frontend/google-drive-ui.test.mjs`, seguindo `tests/frontend/button-radius-ui.test.mjs` (Vite + Playwright, rotas da API interceptadas):
  - `admin sees connect button when disconnected and is sent to auth url`;
  - `admin sees email and disconnect when connected`;
  - `non-admin does not see the drive block`;
  - `connected query param shows success message and is removed from URL`;
  - `upload with GOOGLE_DRIVE_NOT_CONNECTED shows admin and non-admin messages`.
- [ ] **Step 2: Run** `node --test tests/frontend/google-drive-ui.test.mjs`. Esperado: FAIL.
- [ ] **Step 3: Implement** o serviço, o componente e a mudança em `Processos.tsx`.
- [ ] **Step 4: Run** o teste novo, os testes existentes (`node --test tests/frontend/`) e `npm run build`. Esperado: tudo passa e o build sai sem erro de tipo.
- [ ] **Step 5: Commit** `feat: conexão do Google Drive na página de Processos (US09)` e abrir o PR do frontend para a `main`, com a observação de que o PR do backend precisa entrar no ar antes.

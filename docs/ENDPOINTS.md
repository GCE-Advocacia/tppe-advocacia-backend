# Endpoints

Todas as respostas seguem o envelope `APIResponse[T]`. Ver [ARCHITECTURE.md](./ARCHITECTURE.md) para detalhes do padrão.

---

## Health

### `GET /api/v1/health`

Verifica a saúde da API e a conectividade com o banco de dados.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "status": "ok",
    "app_name": "Advocacia API",
    "version": "0.1.0",
    "database": "ok"
  }
}
```

---

## Leads

### `GET /api/v1/leads`

Lista leads com filtros opcionais e paginação.

> Exige autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

**Query params**

| Parâmetro     | Tipo                                                    | Obrigatório | Descrição                        |
| ------------- | ------------------------------------------------------- | ----------- | -------------------------------- |
| `status`      | `novo` \| `em_atendimento` \| `fechado` \| `descartado` | Não         | Filtra por status                |
| `assigned_to` | `integer`                                               | Não         | Filtra por ID do responsável     |
| `page`        | `integer` (≥ 1)                                         | Não         | Página atual (default: `1`)      |
| `limit`       | `integer` (1–100)                                       | Não         | Itens por página (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "João Silva",
      "email": "joao@email.com",
      "phone": "11999999999",
      "message": "Preciso de ajuda.",
      "status": "novo",
      "assigned_to": null,
      "created_at": "2026-05-06T12:00:00Z",
      "updated_at": "2026-05-06T12:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code           | Situação                        |
| ------ | -------------- | ------------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido       |
| 403    | `FORBIDDEN`    | Usuário autenticado não é ADMIN |

---

### `POST /api/v1/leads`

Cria um novo lead originado do formulário de contato. Público — não exige autenticação.

Leads com o mesmo e-mail enviados dentro da janela configurada (`LEAD_DEDUP_WINDOW_HOURS`, padrão: `1h`) são rejeitados com 409.

**Body**

```json
{
  "name": "João Silva",
  "email": "joao@email.com",
  "phone": "11999999999",
  "message": "Preciso de ajuda."
}
```

> `phone` e `message` são opcionais.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "João Silva",
    "email": "joao@email.com",
    "phone": "11999999999",
    "message": "Preciso de ajuda.",
    "status": "novo",
    "assigned_to": null,
    "created_at": "2026-05-06T12:00:00Z",
    "updated_at": "2026-05-06T12:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                                         |
| ------ | ------------------ | ------------------------------------------------ |
| 409    | `LEAD_DUPLICATE`   | Mesmo e-mail submetido dentro da janela de dedup |
| 422    | `VALIDATION_ERROR` | Body inválido                                    |

---

### `PATCH /api/v1/leads/{lead_id}`

Atualiza o status ou o responsável de um lead. Todos os campos são opcionais.

> Quando `assigned_to` muda para um novo responsável diferente do próprio usuário que faz a chamada, é disparada notificação `LEAD_ASSIGNED` (ver seção [Notifications](#notifications) — respeita preferência do destinatário; falha de e-mail não bloqueia a operação).

> Exige autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

**Body**

```json
{
  "status": "em_atendimento",
  "assigned_to": 2
}
```

> `status`: `"novo"` | `"em_atendimento"` | `"fechado"` | `"descartado"`
> `assigned_to`: ID de um usuário cadastrado, ou `null` para desatribuir.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "João Silva",
    "email": "joao@email.com",
    "phone": "11999999999",
    "message": "Preciso de ajuda.",
    "status": "em_atendimento",
    "assigned_to": 2,
    "created_at": "2026-05-06T12:00:00Z",
    "updated_at": "2026-05-06T13:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                        |
| ------ | ------------------ | ------------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido       |
| 403    | `FORBIDDEN`        | Usuário autenticado não é ADMIN |
| 404    | `LEAD_NOT_FOUND`   | Lead não encontrado             |
| 422    | `VALIDATION_ERROR` | Body inválido                   |

---

## Auth

### `POST /api/v1/auth/login`

Autentica um usuário com e-mail e senha e retorna um JWT de acesso.

**Body**

```json
{
  "email": "usuario@email.com",
  "password": "senha123"
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "access_token": "<jwt>",
    "token_type": "bearer"
  }
}
```

**Erros**

| Status | Code                  | Situação                                           |
| ------ | --------------------- | -------------------------------------------------- |
| 401    | `INVALID_CREDENTIALS` | E-mail não encontrado ou senha incorreta           |
| 403    | `INACTIVE_USER`       | Usuário desativado                                 |
| 422    | `VALIDATION_ERROR`    | Body inválido (e-mail malformado, campos ausentes) |

**Resposta de erro (exemplo)**

```json
{
  "success": false,
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Invalid credentials"
  }
}
```

---

### `POST /api/v1/auth/password-reset/request`

Solicita o envio de e-mail com link para redefinição de senha. Sempre retorna 200, mesmo que o e-mail não exista, para não expor se o usuário está cadastrado.

**Body**

```json
{
  "email": "usuario@email.com"
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": null
}
```

**Erros**

| Status | Code               | Situação      |
| ------ | ------------------ | ------------- |
| 422    | `VALIDATION_ERROR` | Body inválido |

---

### `POST /api/v1/auth/password-reset/confirm`

Confirma a redefinição de senha usando o token recebido por e-mail. O token é de uso único e expira após o prazo configurado.

**Body**

```json
{
  "token": "<token-recebido-por-email>",
  "new_password": "novaSenha123"
}
```

> `new_password` deve ter no mínimo 8 caracteres.

**Resposta 200**

```json
{
  "success": true,
  "data": null
}
```

**Erros**

| Status | Code                  | Situação                                |
| ------ | --------------------- | --------------------------------------- |
| 400    | `INVALID_RESET_TOKEN` | Token inválido, inexistente ou expirado |
| 422    | `VALIDATION_ERROR`    | Body inválido                           |

---

## Users

> Todos os endpoints abaixo exigem autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

---

### `GET /api/v1/users`

Lista usuários com filtros opcionais e paginação.

**Query params**

| Parâmetro   | Tipo              | Obrigatório | Descrição                        |
| ----------- | ----------------- | ----------- | -------------------------------- |
| `role`      | `ADMIN` \| `USER` | Não         | Filtra por papel                 |
| `is_active` | `boolean`         | Não         | Filtra por status de ativação    |
| `page`      | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`     | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "Ana Lima",
      "email": "ana@escritorio.com",
      "role": "ADMIN",
      "is_active": true,
      "created_at": "2026-05-06T12:00:00Z",
      "updated_at": "2026-05-06T12:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code           | Situação                        |
| ------ | -------------- | ------------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido       |
| 403    | `FORBIDDEN`    | Usuário autenticado não é ADMIN |

---

### `POST /api/v1/users`

Cria um novo usuário com papel `USER`. O sistema gera uma senha temporária e a envia ao novo usuário por e-mail. Para promover a `ADMIN`, use `PATCH /api/v1/users/{id}` após a criação.

**Body**

```json
{
  "name": "Carlos Souza",
  "email": "carlos@escritorio.com"
}

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 2,
    "name": "Carlos Souza",
    "email": "carlos@escritorio.com",
    "role": "USER",
    "is_active": true,
    "created_at": "2026-05-06T12:00:00Z",
    "updated_at": "2026-05-06T12:00:00Z"
  }
}
```

**Erros**

| Status | Code                   | Situação                        |
| ------ | ---------------------- | ------------------------------- |
| 401    | `UNAUTHORIZED`         | Token ausente ou inválido       |
| 403    | `FORBIDDEN`            | Usuário autenticado não é ADMIN |
| 409    | `EMAIL_ALREADY_EXISTS` | E-mail já cadastrado            |
| 422    | `VALIDATION_ERROR`     | Body inválido                   |

---

### `GET /api/v1/users/{id}`

Retorna os dados de um usuário específico.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 2,
    "name": "Carlos Souza",
    "email": "carlos@escritorio.com",
    "role": "USER",
    "is_active": true,
    "created_at": "2026-05-06T12:00:00Z",
    "updated_at": "2026-05-06T12:00:00Z"
  }
}
```

**Erros**

| Status | Code             | Situação                        |
| ------ | ---------------- | ------------------------------- |
| 401    | `UNAUTHORIZED`   | Token ausente ou inválido       |
| 403    | `FORBIDDEN`      | Usuário autenticado não é ADMIN |
| 404    | `USER_NOT_FOUND` | ID não encontrado               |

---

### `PATCH /api/v1/users/{id}`

Atualiza parcialmente os dados de um usuário. Todos os campos são opcionais.
Usado também para **desativar** (`is_active: false`) e **alterar o papel** (`role`).

**Body**

```json
{
  "name": "Carlos Souza Atualizado",
  "email": "novo@escritorio.com",
  "role": "ADMIN",
  "is_active": false
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 2,
    "name": "Carlos Souza Atualizado",
    "email": "novo@escritorio.com",
    "role": "ADMIN",
    "is_active": false,
    "created_at": "2026-05-06T12:00:00Z",
    "updated_at": "2026-05-06T13:00:00Z"
  }
}
```

---

## Media

> Upload exige autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

### `POST /api/v1/media/upload`

Faz upload de uma imagem. Retorna a URL pública para acesso ao arquivo.

**Content-Type:** `multipart/form-data`

**Body**

| Campo  | Tipo   | Obrigatório | Descrição         |
| ------ | ------ | ----------- | ----------------- |
| `file` | `file` | Sim         | Arquivo de imagem |

**Tamanho máximo:** configurável via `MAX_FILE_SIZE_MB` (padrão: 5 MB)

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "url": "http://localhost:8000/api/v1/media/3f2a1b4c-uuid.jpg"
  }
}
```

**Erros**

| Status | Code                | Situação                                  |
| ------ | ------------------- | ----------------------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido                 |
| 413    | `FILE_TOO_LARGE`    | Arquivo excede o tamanho máximo permitido |
| 415    | `INVALID_MIME_TYPE` | Tipo de arquivo não permitido             |
| 422    | `VALIDATION_ERROR`  | Campo `file` ausente                      |

---

### `GET /api/v1/media/{filename}`

Serve o arquivo de imagem pelo nome retornado no upload. Público — não exige autenticação.

**Path param**

| Parâmetro  | Tipo     | Descrição                           |
| ---------- | -------- | ----------------------------------- |
| `filename` | `string` | Nome do arquivo retornado no upload |

**Resposta 200**

Retorna o binário do arquivo com o `Content-Type` correspondente.

**Erros**

| Status | Code              | Situação               |
| ------ | ----------------- | ---------------------- |
| 404    | `MEDIA_NOT_FOUND` | Arquivo não encontrado |

---

## Audit Logs

> Exige autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

### `GET /api/v1/audit-logs`

Lista logs de auditoria com filtros opcionais e paginação.

**Query params**

| Parâmetro   | Tipo                                                       | Obrigatório | Descrição                            |
| ----------- | ---------------------------------------------------------- | ----------- | ------------------------------------ |
| `action`    | `USER_CREATED` \| `USER_UPDATED` \| `USER_DEACTIVATED` \| `CLIENT_ANONYMIZED` | Não         | Filtra por tipo de ação              |
| `date_from` | `datetime` (ISO 8601)                | Não         | Filtra registros a partir desta data |
| `date_to`   | `datetime` (ISO 8601)                | Não         | Filtra registros até esta data       |
| `page`      | `integer` (≥ 1)                      | Não         | Página atual (default: `1`)          |
| `limit`     | `integer` (1–100)                    | Não         | Itens por página (default: `20`)     |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "action": "USER_CREATED",
      "performed_by_id": 1,
      "performed_by_name": "Ana Lima",
      "target_user_id": 2,
      "target_user_name": "Carlos Souza",
      "target_user_email": "carlos@escritorio.com",
      "target_user_role": "USER",
      "target_client_id": null,
      "target_client_name": null,
      "created_at": "2026-05-16T14:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

> Para `action = "CLIENT_ANONYMIZED"`, os campos `target_user_*` vêm como `null` e `target_client_id`/`target_client_name` (snapshot do nome anterior à anonimização) ficam preenchidos. Para ações de usuário, ocorre o inverso.

**Erros**

| Status | Code           | Situação                        |
| ------ | -------------- | ------------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido       |
| 403    | `FORBIDDEN`    | Usuário autenticado não é ADMIN |

---

## External API Logs

> Exige autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

### `GET /api/v1/external-api-logs`

Lista logs de chamadas a APIs externas, incluindo sucesso/falha do DataJud.

**Query params**

| Parâmetro    | Tipo                  | Obrigatório | Descrição                          |
| ------------ | --------------------- | ----------- | ---------------------------------- |
| `provider`   | `DATAJUD`             | Não         | Filtra por provedor                |
| `status`     | `SUCCESS` \| `FAILURE` | Não         | Filtra por status da chamada       |
| `process_id` | `integer`             | Não         | Filtra por processo                |
| `date_from`  | `datetime` (ISO 8601) | Não         | Filtra registros a partir da data  |
| `date_to`    | `datetime` (ISO 8601) | Não         | Filtra registros até a data        |
| `page`       | `integer` (≥ 1)       | Não         | Página atual (default: `1`)        |
| `limit`      | `integer` (1–100)     | Não         | Itens por página (default: `20`)   |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 10,
      "provider": "DATAJUD",
      "operation": "PROCESS_MOVEMENT_SYNC",
      "status": "FAILURE",
      "process_id": 1,
      "tribunal_alias": "tjsp",
      "request_identifier": "12345678920248260100",
      "http_status": 503,
      "error_code": "DATAJUD_REQUEST_FAILED",
      "error_message": "DataJud returned an error response",
      "created_by": 3,
      "created_at": "2026-05-20T12:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code           | Situação                        |
| ------ | -------------- | ------------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido       |
| 403    | `FORBIDDEN`    | Usuário autenticado não é ADMIN |

---

## Office Config

### `GET /api/v1/office-config`

Retorna a configuração atual do escritório. Público — não exige autenticação.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "office_name": "Escritório Silva Advocacia",
    "cnpj": "00.000.000/0001-00",
    "address": "Rua das Flores, 123, São Paulo - SP",
    "phone": "11999999999",
    "email": "contato@escritorio.com",
    "instagram_url": "https://instagram.com/escritorio",
    "linkedin_url": "https://linkedin.com/company/escritorio",
    "whatsapp_url": "https://wa.me/5511999999999",
    "hero_title": "Defendendo seus direitos",
    "hero_subtitle": "Com experiência e dedicação",
    "hero_image_url": "https://cdn.exemplo.com/hero.jpg",
    "about_title": "Sobre nós",
    "about_description": "Somos um escritório especializado...",
    "about_image_url": "https://cdn.exemplo.com/about.jpg",
    "lawyer_name": "Dr. João Silva",
    "lawyer_oab": "OAB/SP 123456",
    "lawyer_description": "Especialista em direito civil...",
    "lawyer_image_url": "https://cdn.exemplo.com/lawyer.jpg",
    "differentials": [{ "title": "Atendimento humanizado", "description": "..." }],
    "areas_of_practice": [{ "title": "Direito Civil", "description": "..." }]
  }
}
```

---

### `PATCH /api/v1/office-config`

Atualiza parcialmente a configuração do escritório. Todos os campos são opcionais.

> Exige autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

**Body**

```json
{
  "office_name": "Novo Nome",
  "cnpj": "00.000.000/0001-00",
  "address": "Rua Nova, 456, São Paulo - SP",
  "phone": "11988888888",
  "email": "novo@escritorio.com",
  "instagram_url": "https://instagram.com/novo",
  "linkedin_url": "https://linkedin.com/company/novo",
  "whatsapp_url": "https://wa.me/5511988888888",
  "hero_title": "Novo título",
  "hero_subtitle": "Novo subtítulo",
  "hero_image_url": "https://cdn.exemplo.com/hero-novo.jpg",
  "about_title": "Sobre nós atualizado",
  "about_description": "Descrição atualizada...",
  "about_image_url": "https://cdn.exemplo.com/about-novo.jpg",
  "lawyer_name": "Dra. Maria Santos",
  "lawyer_oab": "OAB/SP 654321",
  "lawyer_description": "Especialista em direito de família...",
  "lawyer_image_url": "https://cdn.exemplo.com/lawyer-novo.jpg",
  "differentials": [{ "title": "Agilidade", "description": "Respostas rápidas" }],
  "areas_of_practice": [{ "title": "Direito de Família", "description": "..." }]
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "office_name": "Novo Nome",
    "..."
  }
}
```

**Erros**

| Status | Code           | Situação                        |
| ------ | -------------- | ------------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido       |
| 403    | `FORBIDDEN`    | Usuário autenticado não é ADMIN |

---

## Articles

### `POST /api/v1/articles`

Cria um novo artigo. O autor é o usuário autenticado.

> Exige autenticação. Header: `Authorization: Bearer <token>`

**Body**

```json
{
  "title": "Direitos do Consumidor",
  "content": "Conteúdo completo do artigo...",
  "category": "Direito Civil",
  "summary": "Resumo opcional do artigo",
  "cover_image_url": "https://cdn.exemplo.com/capa.jpg",
  "status": "draft"
}
```

> `status`: `"draft"` (padrão) ou `"published"`. Campo `cover_image_url` é opcional.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Direitos do Consumidor",
    "content": "Conteúdo completo do artigo...",
    "category": "Direito Civil",
    "summary": "Resumo opcional do artigo",
    "cover_image_url": "https://cdn.exemplo.com/capa.jpg",
    "status": "draft",
    "author_id": 3,
    "author_name": "Dr. João Silva",
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T14:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                  |
| ------ | ------------------ | ------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido |
| 422    | `VALIDATION_ERROR` | Body inválido             |

---

### `PATCH /api/v1/articles/{article_id}`

Atualiza parcialmente um artigo. Todos os campos são opcionais. Usado também para publicar (`status: "published"`) ou reverter para rascunho (`status: "draft"`).

> Exige autenticação. Header: `Authorization: Bearer <token>`

**Body**

```json
{
  "title": "Título Atualizado",
  "content": "Novo conteúdo...",
  "category": "Direito Trabalhista",
  "summary": "Novo resumo",
  "cover_image_url": "https://cdn.exemplo.com/nova-capa.jpg",
  "status": "published"
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Título Atualizado",
    "content": "Novo conteúdo...",
    "category": "Direito Trabalhista",
    "summary": "Novo resumo",
    "cover_image_url": "https://cdn.exemplo.com/nova-capa.jpg",
    "status": "published",
    "author_id": 3,
    "author_name": "Dr. João Silva",
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T15:00:00Z"
  }
}
```

**Erros**

| Status | Code                | Situação                  |
| ------ | ------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido |
| 404    | `ARTICLE_NOT_FOUND` | Artigo não encontrado     |
| 422    | `VALIDATION_ERROR`  | Body inválido             |

---

### `GET /api/v1/articles`

Lista artigos publicados com paginação. Público — não exige autenticação.

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                        |
| --------- | ----------------- | ----------- | -------------------------------- |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "title": "Direitos do Consumidor",
      "summary": "Resumo do artigo",
      "status": "published",
      "created_at": "2026-05-16T14:00:00Z",
      "url": "http://api.exemplo.com/api/v1/articles/1"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

---

### `GET /api/v1/articles/{article_id}`

Retorna um artigo publicado pelo ID. Público — não exige autenticação. Retorna 404 se o artigo for rascunho.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Direitos do Consumidor",
    "content": "Conteúdo completo do artigo...",
    "category": "Direito Civil",
    "summary": "Resumo do artigo",
    "cover_image_url": "https://cdn.exemplo.com/capa.jpg",
    "status": "published",
    "author_id": 3,
    "author_name": "Dr. João Silva",
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                | Situação                                |
| ------ | ------------------- | --------------------------------------- |
| 404    | `ARTICLE_NOT_FOUND` | Artigo não encontrado ou ainda rascunho |

---

### `GET /api/v1/articles/{article_id}/preview`

Retorna um artigo independente do status (rascunho ou publicado). Usado para preview antes de publicar.

> Exige autenticação. Header: `Authorization: Bearer <token>`

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Direitos do Consumidor",
    "content": "Conteúdo completo do artigo...",
    "category": "Direito Civil",
    "summary": null,
    "cover_image_url": null,
    "status": "draft",
    "author_id": 3,
    "author_name": "Dr. João Silva",
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                | Situação                  |
| ------ | ------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido |
| 404    | `ARTICLE_NOT_FOUND` | Artigo não encontrado     |

---

### `GET /api/v1/articles/admin`

Lista todos os artigos incluindo rascunhos, com paginação. URLs dos itens apontam para o endpoint de preview.

> Exige autenticação. Header: `Authorization: Bearer <token>`

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                        |
| --------- | ----------------- | ----------- | -------------------------------- |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 2,
      "title": "Artigo em Rascunho",
      "summary": null,
      "status": "draft",
      "created_at": "2026-05-16T13:00:00Z",
      "url": "http://api.exemplo.com/api/v1/articles/2/preview"
    }
  ],
  "meta": {
    "total": 5,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

## Clients

> Todos os endpoints exigem autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

---

### `POST /api/v1/clients`

Cria um novo cliente. CPF e CNPJ são mutuamente exclusivos — exatamente um deve ser informado. Ambos devem ser enviados sem formatação (só dígitos).

**Body**

```json
{
  "name": "João Silva",
  "email": "joao@email.com",
  "phone": "11999999999",
  "cpf": "12345678901",
  "address": "Rua das Flores, 123, São Paulo - SP"
}
```

> `email`, `phone` e `address` são opcionais.
> Usar `cnpj` (14 dígitos) no lugar de `cpf` (11 dígitos) para pessoa jurídica.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "João Silva",
    "email": "joao@email.com",
    "phone": "11999999999",
    "cpf": "12345678901",
    "cnpj": null,
    "address": "Rua das Flores, 123, São Paulo - SP",
    "created_by": 3,
    "updated_by": 3,
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                         | Situação                          |
| ------ | ---------------------------- | --------------------------------- |
| 401    | `UNAUTHORIZED`               | Token ausente ou inválido         |
| 409    | `CLIENT_CPF_ALREADY_EXISTS`  | CPF já cadastrado                 |
| 409    | `CLIENT_CNPJ_ALREADY_EXISTS` | CNPJ já cadastrado                |
| 422    | `VALIDATION_ERROR`           | Body inválido ou CPF/CNPJ ausente |

---

### `GET /api/v1/clients`

Lista clientes com paginação e busca opcional por nome (parcial, case-insensitive) ou CPF/CNPJ (exato).

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                                     |
| --------- | ----------------- | ----------- | --------------------------------------------- |
| `search`  | `string`          | Não         | Filtra por nome (parcial) ou CPF/CNPJ (exato) |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)                   |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`)              |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "name": "João Silva",
      "email": "joao@email.com",
      "phone": "11999999999",
      "cpf": "12345678901",
      "cnpj": null
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `GET /api/v1/clients/{id}`

Retorna dados completos de um cliente. Quando o cliente foi anonimizado (`deleted_at != null`), usuários com role `USER` recebem 404; role `ADMIN` recebe 200 com os campos PII zerados.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "João Silva",
    "email": "joao@email.com",
    "phone": "11999999999",
    "cpf": "12345678901",
    "cnpj": null,
    "address": "Rua das Flores, 123, São Paulo - SP",
    "created_by": 3,
    "updated_by": 5,
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T15:00:00Z",
    "deleted_at": null
  }
}
```

**Erros**

| Status | Code               | Situação                  |
| ------ | ------------------ | ------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido |
| 404    | `CLIENT_NOT_FOUND` | Cliente não encontrado    |

---

### `DELETE /api/v1/clients/{id}`

Anonimiza um cliente (soft delete) em conformidade com a LGPD: sobrescreve todos os campos PII (`name = "[ANONIMIZADO]"`, `email/phone/cpf/cnpj/address = null`), seta `deleted_at = now()` e anonimiza também o conteúdo de todas as notas (`client_notes.content = "[ANONIMIZADO]"`). Ação irreversível.

> Exige autenticação com role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

**Query params**

| Parâmetro | Tipo      | Obrigatório | Descrição                                                |
| --------- | --------- | ----------- | -------------------------------------------------------- |
| `confirm` | `boolean` | Sim         | Deve ser `true`. Confirmação explícita da ação irreversível. |

**Resposta 204** — sem corpo.

Efeitos colaterais:

- Cliente deixa de aparecer em `GET /clients` e em buscas por `search` (inclusive para ADMIN).
- `GET /clients/{id}` retorna 404 para role `USER`; para `ADMIN`, retorna 200 com dados anonimizados e `deleted_at` preenchido.
- Processos vinculados permanecem intactos; em todos os endpoints de `processes`, `client_name` aparece como `"[ANONIMIZADO]"`.
- CPF/CNPJ originais ficam liberados para reuso por um novo cadastro (unique constraint libera porque os valores são setados para `null`).
- Audit log com `action = "CLIENT_ANONYMIZED"` é registrado contendo `performed_by_id`, `performed_by_name`, `target_client_id` e `target_client_name` (snapshot do nome anterior à anonimização).

**Erros**

| Status | Code                          | Situação                                                                 |
| ------ | ----------------------------- | ------------------------------------------------------------------------ |
| 400    | `CONFIRMATION_REQUIRED`       | `?confirm=true` ausente ou diferente de `true`                          |
| 401    | `UNAUTHORIZED`                | Token ausente ou inválido                                                |
| 403    | `FORBIDDEN`                   | Usuário autenticado não é ADMIN                                          |
| 404    | `CLIENT_NOT_FOUND`            | Cliente não encontrado ou já anonimizado                                 |
| 409    | `CLIENT_HAS_ACTIVE_PROCESSES` | Cliente possui processo com status `ATIVO` ou `SUSPENSO`                 |

---

### `PATCH /api/v1/clients/{id}`

Atualiza parcialmente um cliente. Todos os campos são opcionais. Não é permitido enviar `cpf` e `cnpj` simultaneamente.

**Body**

```json
{
  "name": "João Silva Atualizado",
  "email": "novo@email.com",
  "phone": "11988888888",
  "address": "Av. Paulista, 1000, São Paulo - SP"
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "name": "João Silva Atualizado",
    "email": "novo@email.com",
    "phone": "11988888888",
    "cpf": "12345678901",
    "cnpj": null,
    "address": "Av. Paulista, 1000, São Paulo - SP",
    "created_by": 3,
    "updated_by": 5,
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T15:00:00Z"
  }
}
```

**Erros**

| Status | Code                         | Situação                           |
| ------ | ---------------------------- | ---------------------------------- |
| 401    | `UNAUTHORIZED`               | Token ausente ou inválido          |
| 404    | `CLIENT_NOT_FOUND`           | Cliente não encontrado             |
| 409    | `CLIENT_CPF_ALREADY_EXISTS`  | CPF já pertence a outro cliente    |
| 409    | `CLIENT_CNPJ_ALREADY_EXISTS` | CNPJ já pertence a outro cliente   |
| 422    | `VALIDATION_ERROR`           | Body inválido ou CPF e CNPJ juntos |

---

### `POST /api/v1/clients/{client_id}/notes`

Cria uma observação interna vinculada ao cliente. O autor é o usuário autenticado.

**Body**

```json
{
  "content": "Cliente prefere contato por WhatsApp."
}
```

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "client_id": 7,
    "created_by": 3,
    "updated_by": null,
    "created_by_name": "Ana Lima",
    "updated_by_name": null,
    "content": "Cliente prefere contato por WhatsApp.",
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T14:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                   |
| ------ | ------------------ | -------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido  |
| 404    | `CLIENT_NOT_FOUND` | Cliente não encontrado     |
| 422    | `VALIDATION_ERROR` | `content` ausente ou vazio |

---

### `GET /api/v1/clients/{client_id}/notes`

Lista todas as observações do cliente em ordem cronológica decrescente (mais recente primeiro), com paginação.

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                        |
| --------- | ----------------- | ----------- | -------------------------------- |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 2,
      "client_id": 7,
      "created_by": 5,
      "updated_by": 3,
      "created_by_name": "Carlos Souza",
      "updated_by_name": "Ana Lima",
      "content": "Reunião agendada para segunda-feira.",
      "created_at": "2026-05-16T15:00:00Z",
      "updated_at": "2026-05-16T16:00:00Z"
    },
    {
      "id": 1,
      "client_id": 7,
      "created_by": 3,
      "updated_by": null,
      "created_by_name": "Ana Lima",
      "updated_by_name": null,
      "content": "Cliente prefere contato por WhatsApp.",
      "created_at": "2026-05-16T14:00:00Z",
      "updated_at": "2026-05-16T14:00:00Z"
    }
  ],
  "meta": {
    "total": 2,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code               | Situação                  |
| ------ | ------------------ | ------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido |
| 404    | `CLIENT_NOT_FOUND` | Cliente não encontrado    |

---

### `PATCH /api/v1/clients/{client_id}/notes/{note_id}`

Edita o conteúdo de uma observação. Apenas o autor original pode editar; usuários com role `ADMIN` podem editar qualquer observação.

**Body**

```json
{
  "content": "Cliente prefere contato por e-mail, não WhatsApp."
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "client_id": 7,
    "created_by": 3,
    "updated_by": 3,
    "created_by_name": "Ana Lima",
    "updated_by_name": "Ana Lima",
    "content": "Cliente prefere contato por e-mail, não WhatsApp.",
    "created_at": "2026-05-16T14:00:00Z",
    "updated_at": "2026-05-16T17:00:00Z"
  }
}
```

**Erros**

| Status | Code                    | Situação                                             |
| ------ | ----------------------- | ---------------------------------------------------- |
| 401    | `UNAUTHORIZED`          | Token ausente ou inválido                            |
| 403    | `FORBIDDEN`             | Usuário não é o autor nem ADMIN                      |
| 404    | `CLIENT_NOT_FOUND`      | Cliente não encontrado                               |
| 404    | `CLIENT_NOTE_NOT_FOUND` | Observação não encontrada ou não pertence ao cliente |
| 422    | `VALIDATION_ERROR`      | `content` ausente ou vazio                           |

---

### `GET /api/v1/clients/{client_id}/timeline`

Retorna visão 360º do cliente: dados do cliente, notas recentes, processos vinculados (com última movimentação) e feed de atividades recentes (movimentações + notas mescladas e ordenadas por data).

**Query params**

| Parâmetro         | Tipo             | Obrigatório | Descrição                                                 |
| ----------------- | ---------------- | ----------- | --------------------------------------------------------- |
| `notes_limit`     | `integer` (1–50) | Não         | Máx. notas recentes do cliente (default: `10`)            |
| `processes_limit` | `integer` (1–50) | Não         | Máx. processos retornados (default: `20`)                 |
| `activity_limit`  | `integer` (1–50) | Não         | Máx. itens no feed de atividades recentes (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "client": {
      "id": 7,
      "name": "João Silva",
      "email": "joao@email.com",
      "phone": "11999999999",
      "cpf": "12345678901",
      "cnpj": null,
      "address": "Rua das Flores, 123, São Paulo - SP",
      "created_by": 3,
      "updated_by": 3,
      "created_at": "2026-05-16T14:00:00Z",
      "updated_at": "2026-05-16T14:00:00Z"
    },
    "notes": [
      {
        "id": 1,
        "client_id": 7,
        "created_by": 3,
        "updated_by": null,
        "created_by_name": "Ana Lima",
        "updated_by_name": null,
        "content": "Cliente prefere contato por WhatsApp.",
        "created_at": "2026-05-16T14:00:00Z",
        "updated_at": "2026-05-16T14:00:00Z"
      }
    ],
    "processes": [
      {
        "id": 1,
        "number": "1234567-89.2024.8.26.0100",
        "action_type": "Ação Cível",
        "court": "TJSP",
        "status": "ATIVO",
        "created_at": "2026-05-17T14:00:00Z",
        "last_movement": {
          "id": 2,
          "title": "Petição inicial protocolada",
          "occurred_at": "2026-05-15T09:00:00Z",
          "source": "MANUAL"
        }
      }
    ],
    "recent_activity": [
      {
        "kind": "movement",
        "process_id": 1,
        "note_id": null,
        "title": "Petição inicial protocolada",
        "content": null,
        "occurred_at": "2026-05-15T09:00:00Z",
        "actor_id": 3,
        "actor_name": "Ana Lima"
      },
      {
        "kind": "client_note",
        "process_id": null,
        "note_id": 1,
        "title": null,
        "content": "Cliente prefere contato por WhatsApp.",
        "occurred_at": "2026-05-16T14:00:00Z",
        "actor_id": 3,
        "actor_name": "Ana Lima"
      }
    ]
  }
}
```

> `notes` ordenadas por `created_at DESC`. `processes` ordenados por `created_at DESC`; `last_movement` é `null` quando o processo não tem movimentações. `recent_activity` mescla movimentações de todos os processos do cliente e notas do cliente, ordenado por `occurred_at DESC`. `kind` indica a origem: `"movement"` (movimentação de processo) ou `"client_note"` (observação do cliente).

**Erros**

| Status | Code               | Situação                  |
| ------ | ------------------ | ------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido |
| 404    | `CLIENT_NOT_FOUND` | Cliente não encontrado    |

---

## Processes

> Todos os endpoints exigem autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

O campo `number` segue o padrão CNJ. Aceita tanto a forma mascarada (`NNNNNNN-DD.AAAA.J.TR.OOOO`) quanto apenas 20 dígitos no envio. Persistido como dígitos puros, retornado sempre mascarado.

---

### `POST /api/v1/processes`

Cria um novo processo judicial. Vincular a um cliente é opcional.

**Body**

```json
{
  "number": "1234567-89.2024.8.26.0100",
  "client_id": 7,
  "court": "TJSP",
  "tribunal_alias": "tjsp",
  "action_type": "Ação Cível",
  "opposing_party": "Empresa X"
}
```

> `client_id`, `tribunal_alias` e `opposing_party` são opcionais. `tribunal_alias` identifica o tribunal na API pública do DataJud (ex.: `tjsp`, `trf-1`) e é usado no sync automático/manual.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "number": "1234567-89.2024.8.26.0100",
    "client_id": 7,
    "client_name": "João Silva",
    "court": "TJSP",
    "tribunal_alias": "tjsp",
    "action_type": "Ação Cível",
    "opposing_party": "Empresa X",
    "status": "ATIVO",
    "created_by": 3,
    "updated_by": 3,
    "created_at": "2026-05-17T14:00:00Z",
    "updated_at": "2026-05-17T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                            | Situação                               |
| ------ | ------------------------------- | -------------------------------------- |
| 401    | `UNAUTHORIZED`                  | Token ausente ou inválido              |
| 409    | `PROCESS_NUMBER_ALREADY_EXISTS` | Número CNJ já cadastrado               |
| 422    | `CLIENT_NOT_FOUND_FOR_PROCESS`  | `client_id` informado não existe       |
| 422    | `VALIDATION_ERROR`              | Body inválido ou número CNJ malformado |

---

### `GET /api/v1/processes`

Lista processos com filtros e paginação. Ordenado por `created_at DESC, id DESC`.

**Query params**

| Parâmetro   | Tipo                                                | Obrigatório | Descrição                                  |
| ----------- | --------------------------------------------------- | ----------- | ------------------------------------------ |
| `client_id` | `integer`                                           | Não         | Filtra por cliente                         |
| `status`    | `ATIVO` \| `SUSPENSO` \| `ARQUIVADO` \| `ENCERRADO` | Não         | Filtra por status                          |
| `search`    | `string`                                            | Não         | Busca parcial em `number` ou `action_type` |
| `page`      | `integer` (≥ 1)                                     | Não         | Página atual (default: `1`)                |
| `limit`     | `integer` (1–100)                                   | Não         | Itens por página (default: `20`)           |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "number": "1234567-89.2024.8.26.0100",
      "client_id": 7,
      "client_name": "João Silva",
      "court": "TJSP",
      "tribunal_alias": "tjsp",
      "action_type": "Ação Cível",
      "status": "ATIVO",
      "created_at": "2026-05-17T14:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `GET /api/v1/processes/{process_id}`

Retorna dados completos de um processo.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "number": "1234567-89.2024.8.26.0100",
    "client_id": 7,
    "client_name": "João Silva",
    "court": "TJSP",
    "tribunal_alias": "tjsp",
    "action_type": "Ação Cível",
    "opposing_party": "Empresa X",
    "status": "ATIVO",
    "created_by": 3,
    "updated_by": 3,
    "created_at": "2026-05-17T14:00:00Z",
    "updated_at": "2026-05-17T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                | Situação                  |
| ------ | ------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido |
| 404    | `PROCESS_NOT_FOUND` | Processo não encontrado   |

---

### `GET /api/v1/clients/{client_id}/processes`

Lista processos vinculados a um cliente específico, com paginação.

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                        |
| --------- | ----------------- | ----------- | -------------------------------- |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Resposta 200**

Mesmo formato de `GET /api/v1/processes`.

**Erros**

| Status | Code               | Situação                  |
| ------ | ------------------ | ------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido |
| 404    | `CLIENT_NOT_FOUND` | Cliente não encontrado    |

---

### `POST /api/v1/processes/{process_id}/movements`

Registra uma movimentação manual no processo. Movimentações são imutáveis — tentativas de `PATCH`/`DELETE` retornam 405.

> Dispara notificação `PROCESS_MOVEMENT_CREATED` para usuários vinculados ao processo (atualmente: `created_by`), exceto o próprio autor da movimentação. Respeita as preferências do destinatário; falha de e-mail não bloqueia a criação.

**Body**

```json
{
  "title": "Audiência de conciliação marcada",
  "description": "Audiência designada para 30/06/2026 às 14h.",
  "occurred_at": "2026-05-17T10:30:00Z"
}
```

> `description` é opcional (até 5000 caracteres). `occurred_at` é opcional — default = `now()` em UTC. Não pode estar no futuro.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "process_id": 1,
    "title": "Audiência de conciliação marcada",
    "description": "Audiência designada para 30/06/2026 às 14h.",
    "occurred_at": "2026-05-17T10:30:00Z",
    "source": "MANUAL",
    "external_id": null,
    "created_by": 3,
    "created_by_name": "Ana Lima",
    "created_at": "2026-05-17T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                | Situação                                                      |
| ------ | ------------------- | ------------------------------------------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido                                     |
| 404    | `PROCESS_NOT_FOUND` | Processo não encontrado                                       |
| 422    | `VALIDATION_ERROR`  | `title` vazio/>150, `description` >5000, `occurred_at` futuro |

---

### `GET /api/v1/processes/{process_id}/movements`

Lista movimentações do processo em ordem cronológica decrescente (`occurred_at DESC, id DESC`), com paginação e filtros.

**Query params**

| Parâmetro   | Tipo                  | Obrigatório | Descrição                         |
| ----------- | --------------------- | ----------- | --------------------------------- |
| `source`    | `MANUAL` \| `SYSTEM`  | Não         | Filtra por origem da movimentação |
| `date_from` | `datetime` (ISO 8601) | Não         | Filtra `occurred_at >= date_from` |
| `date_to`   | `datetime` (ISO 8601) | Não         | Filtra `occurred_at <= date_to`   |
| `page`      | `integer` (≥ 1)       | Não         | Página atual (default: `1`)       |
| `limit`     | `integer` (1–100)     | Não         | Itens por página (default: `20`)  |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 2,
      "process_id": 1,
      "title": "Petição inicial protocolada",
      "description": null,
      "occurred_at": "2026-05-15T09:00:00Z",
      "source": "MANUAL",
      "external_id": null,
      "created_by": 3,
      "created_by_name": "Ana Lima",
      "created_at": "2026-05-17T14:05:00Z"
    },
    {
      "id": 1,
      "process_id": 1,
      "title": "Processo cadastrado",
      "description": null,
      "occurred_at": "2026-05-10T08:00:00Z",
      "source": "SYSTEM",
      "external_id": null,
      "created_by": 3,
      "created_by_name": "Ana Lima",
      "created_at": "2026-05-17T14:00:00Z"
    }
  ],
  "meta": {
    "total": 2,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code                | Situação                  |
| ------ | ------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido |
| 404    | `PROCESS_NOT_FOUND` | Processo não encontrado   |

---

### `POST /api/v1/processes/{process_id}/sync`

Sincroniza movimentações do processo com a API pública do DataJud. As movimentações importadas são persistidas em `process_movements` com `source = SYSTEM` e `external_id` preenchido para deduplicação por processo.

> Se `tribunal_alias` não for enviado no body, a API usa o `tribunal_alias` salvo no processo. Falhas são registradas em `external_api_logs`; falhas de integração também disparam `EXTERNAL_API_FAILURE` para admins ativos.

**Body**

```json
{
  "tribunal_alias": "tjsp"
}
```

> Body opcional. `tribunal_alias` aceita letras minúsculas/números/hífen, de 2 a 30 caracteres.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "process_id": 1,
    "process_number": "1234567-89.2024.8.26.0100",
    "tribunal_alias": "tjsp",
    "imported_count": 1,
    "skipped_count": 0,
    "external_api_log_id": 10,
    "synced_at": "2026-05-20T12:00:00Z",
    "movements": [
      {
        "id": 3,
        "process_id": 1,
        "title": "Conclusos para decisão",
        "description": "Importado do DataJud",
        "occurred_at": "2026-05-20T10:00:00Z",
        "source": "SYSTEM",
        "external_id": "2f1c...",
        "created_by": 3,
        "created_by_name": "Ana Lima",
        "created_at": "2026-05-20T12:00:00Z"
      }
    ]
  }
}
```

**Erros**

| Status | Code                              | Situação                                      |
| ------ | --------------------------------- | --------------------------------------------- |
| 401    | `UNAUTHORIZED`                    | Token ausente ou inválido                     |
| 404    | `PROCESS_NOT_FOUND`               | Processo não encontrado                       |
| 404    | `DATAJUD_PROCESS_NOT_FOUND`       | DataJud não retornou o processo               |
| 422    | `DATAJUD_TRIBUNAL_ALIAS_REQUIRED` | Processo sem tribunal DataJud salvo/fornecido |
| 502    | `DATAJUD_UNAVAILABLE`             | Falha na chamada ao DataJud                   |
| 503    | `DATAJUD_NOT_CONFIGURED`          | `DATAJUD_API_KEY` não configurada             |

---

### `POST /api/v1/datajud/sync-active-processes`

Sincroniza em lote processos com `status = ATIVO`. Quando `tribunal_alias` é omitido, somente processos ativos com `tribunal_alias` salvo são varridos.

> Exige autenticação com role `ADMIN`.

**Body**

```json
{
  "tribunal_alias": null,
  "limit": 50
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "tribunal_alias": null,
    "total_active_processes": 12,
    "processed_count": 12,
    "success_count": 11,
    "failure_count": 1,
    "imported_count": 18,
    "skipped_count": 7,
    "synced_at": "2026-05-20T12:00:00Z",
    "results": []
  }
}
```

**Erros**

| Status | Code                  | Situação                        |
| ------ | --------------------- | ------------------------------- |
| 401    | `UNAUTHORIZED`        | Token ausente ou inválido       |
| 403    | `FORBIDDEN`           | Usuário autenticado não é ADMIN |
| 422    | `VALIDATION_ERROR`    | Body inválido                   |
| 502    | `DATAJUD_UNAVAILABLE` | Falha geral na chamada DataJud  |

---

### `PATCH /api/v1/processes/{process_id}/status`

Altera o status do processo e registra automaticamente uma movimentação `SYSTEM` na timeline. Toda transição entre os 4 valores é permitida (sem máquina de estados rígida). A atualização do processo e a criação da movimentação ocorrem na mesma transação — se uma falhar, nenhuma persiste.

> Dispara notificação `PROCESS_STATUS_CHANGED` para usuários vinculados ao processo (atualmente: `created_by`), exceto quem executou a alteração. Respeita preferências; falha de e-mail não bloqueia a alteração.

**Body**

```json
{
  "status": "SUSPENSO",
  "reason": "Aguardando acordo extrajudicial."
}
```

> `status`: `"ATIVO"` | `"SUSPENSO"` | `"ARQUIVADO"` | `"ENCERRADO"`.
> `reason` é opcional (até 500 caracteres) e fica gravado como `description` na movimentação automática.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "number": "1234567-89.2024.8.26.0100",
    "client_id": 7,
    "client_name": "João Silva",
    "court": "TJSP",
    "action_type": "Ação Cível",
    "opposing_party": "Empresa X",
    "status": "SUSPENSO",
    "created_by": 3,
    "updated_by": 5,
    "created_at": "2026-05-17T14:00:00Z",
    "updated_at": "2026-05-17T16:00:00Z",
    "last_status_change_movement_id": 42
  }
}
```

> `last_status_change_movement_id` aponta para a movimentação `SYSTEM` criada automaticamente, com `title = "Status alterado: <ANTERIOR> -> <NOVO>"` e `description = reason` (quando informado).

**Erros**

| Status | Code                        | Situação                                              |
| ------ | --------------------------- | ----------------------------------------------------- |
| 401    | `UNAUTHORIZED`              | Token ausente ou inválido                             |
| 404    | `PROCESS_NOT_FOUND`         | Processo não encontrado                               |
| 409    | `PROCESS_STATUS_UNCHANGED`  | Status enviado é igual ao status atual (idempotência) |
| 422    | `VALIDATION_ERROR`          | `status` fora do enum ou `reason` > 500 caracteres    |

---

### `POST /api/v1/processes/{process_id}/notes`

Cria uma anotação interna vinculada ao processo. O autor é o usuário autenticado. Notas são separadas das movimentações — não aparecem em `GET /processes/{id}/movements`.

**Body**

```json
{
  "content": "Estratégia: aguardar prazo recursal antes de protocolar contestação."
}
```

> `content` obrigatório, 1–5000 caracteres.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "process_id": 1,
    "created_by": 3,
    "updated_by": null,
    "created_by_name": "Ana Lima",
    "updated_by_name": null,
    "content": "Estratégia: aguardar prazo recursal antes de protocolar contestação.",
    "created_at": "2026-05-17T14:00:00Z",
    "updated_at": "2026-05-17T14:00:00Z"
  }
}
```

**Erros**

| Status | Code                | Situação                                       |
| ------ | ------------------- | ---------------------------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido                      |
| 404    | `PROCESS_NOT_FOUND` | Processo não encontrado                        |
| 422    | `VALIDATION_ERROR`  | `content` ausente, vazio ou > 5000 caracteres  |

---

### `GET /api/v1/processes/{process_id}/notes`

Lista anotações internas do processo em ordem cronológica decrescente (`created_at DESC, id DESC`), com paginação.

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                        |
| --------- | ----------------- | ----------- | -------------------------------- |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 2,
      "process_id": 1,
      "created_by": 5,
      "updated_by": 3,
      "created_by_name": "Carlos Souza",
      "updated_by_name": "Ana Lima",
      "content": "Cliente confirmou disponibilidade para audiência.",
      "created_at": "2026-05-17T15:00:00Z",
      "updated_at": "2026-05-17T16:00:00Z"
    },
    {
      "id": 1,
      "process_id": 1,
      "created_by": 3,
      "updated_by": null,
      "created_by_name": "Ana Lima",
      "updated_by_name": null,
      "content": "Estratégia: aguardar prazo recursal antes de protocolar contestação.",
      "created_at": "2026-05-17T14:00:00Z",
      "updated_at": "2026-05-17T14:00:00Z"
    }
  ],
  "meta": {
    "total": 2,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

**Erros**

| Status | Code                | Situação                  |
| ------ | ------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido |
| 404    | `PROCESS_NOT_FOUND` | Processo não encontrado   |

---

## Notifications

> Todos os endpoints exigem autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

Tipos de evento suportados: `PROCESS_MOVEMENT_CREATED`, `PROCESS_STATUS_CHANGED`, `LEAD_ASSIGNED`, `TASK_ASSIGNED`, `DEADLINE_APPROACHING`, `DEADLINE_EXPIRED`, `EXTERNAL_API_FAILURE`.
Default para qualquer evento sem registro explícito é `true` (notificação habilitada).

**Regras de disparo:**

- O usuário que causou o evento (criador da movimentação, autor da mudança de status, quem fez a atribuição) **não** recebe notificação por essa ação.
- Falhas no envio (preferências indisponíveis, e-mail caiu, template inválido) são engolidas e logadas — **nunca** bloqueiam a operação principal (criar movimentação, alterar status, etc.).
- Os disparos acontecem após o commit da operação principal. Não há rollback de DB causado por falha de notificação.

**Endpoints que disparam:**

| Endpoint                                       | Evento                       | Destinatários atuais                  |
| ---------------------------------------------- | ---------------------------- | ------------------------------------- |
| `POST /processes`                              | `PROCESS_MOVEMENT_CREATED`*  | `process.created_by`                  |
| `POST /processes/{id}/movements`               | `PROCESS_MOVEMENT_CREATED`   | `process.created_by`                  |
| `PATCH /processes/{id}/status`                 | `PROCESS_STATUS_CHANGED`     | `process.created_by`                  |
| `PATCH /leads/{id}` (mudou `assigned_to`)      | `LEAD_ASSIGNED`              | novo `assigned_to`                    |
| `POST /tasks` / `PATCH /tasks/{id}`            | `TASK_ASSIGNED`              | `assigned_to` quando definido/alterado |
| Job cron diário de prazos                      | `DEADLINE_APPROACHING`       | `deadline.created_by`                 |
| Job cron diário de prazos                      | `DEADLINE_EXPIRED`           | `deadline.created_by`                 |
| Falha em integração externa                    | `EXTERNAL_API_FAILURE`       | admins ativos                         |

\* Como o próprio criador é o autor, na prática ninguém é notificado pela movimentação inicial — o disparo fica em pé para o futuro (ex.: quando houver "responsável pelo processo" diferente do criador).

Os eventos `DEADLINE_APPROACHING` / `DEADLINE_EXPIRED` não são disparados por um endpoint HTTP, mas por um job agendado (APScheduler) — ver seção [Deadlines](#deadlines).

---

### `GET /api/v1/notifications/preferences`

Retorna as preferências de notificação do usuário autenticado. Todos os tipos de evento são sempre retornados; tipos sem registro explícito vêm com `true`.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "preferences": {
      "PROCESS_MOVEMENT_CREATED": true,
      "PROCESS_STATUS_CHANGED": true,
      "LEAD_ASSIGNED": true,
      "TASK_ASSIGNED": true,
      "DEADLINE_APPROACHING": true,
      "DEADLINE_EXPIRED": true,
      "EXTERNAL_API_FAILURE": true
    }
  }
}
```

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `PATCH /api/v1/notifications/preferences`

Atualiza preferências do usuário autenticado. Atualização parcial — só os tipos enviados são modificados. Retorna o estado completo após o update.

**Body**

```json
{
  "preferences": {
    "LEAD_ASSIGNED": false,
    "TASK_ASSIGNED": true
  }
}
```

> `preferences` é obrigatório e não pode ser vazio. Chaves devem ser tipos de evento válidos.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "preferences": {
      "PROCESS_MOVEMENT_CREATED": true,
      "PROCESS_STATUS_CHANGED": true,
      "LEAD_ASSIGNED": false,
      "TASK_ASSIGNED": true
    }
  }
}
```

**Erros**

| Status | Code               | Situação                                              |
| ------ | ------------------ | ----------------------------------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido                             |
| 422    | `VALIDATION_ERROR` | Body inválido, `preferences` vazio ou evento inválido |

---

### `PATCH /api/v1/processes/{process_id}/notes/{note_id}`

Edita o conteúdo de uma anotação. Apenas o autor original pode editar; usuários com role `ADMIN` podem editar qualquer anotação.

**Body**

```json
{
  "content": "Estratégia revista: solicitar perícia técnica antes da audiência."
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "process_id": 1,
    "created_by": 3,
    "updated_by": 3,
    "created_by_name": "Ana Lima",
    "updated_by_name": "Ana Lima",
    "content": "Estratégia revista: solicitar perícia técnica antes da audiência.",
    "created_at": "2026-05-17T14:00:00Z",
    "updated_at": "2026-05-17T17:00:00Z"
  }
}
```

**Erros**

| Status | Code                     | Situação                                              |
| ------ | ------------------------ | ----------------------------------------------------- |
| 401    | `UNAUTHORIZED`           | Token ausente ou inválido                             |
| 403    | `FORBIDDEN`              | Usuário não é o autor nem ADMIN                       |
| 404    | `PROCESS_NOT_FOUND`      | Processo não encontrado                               |
| 404    | `PROCESS_NOTE_NOT_FOUND` | Anotação não encontrada ou não pertence ao processo   |
| 422    | `VALIDATION_ERROR`       | `content` ausente, vazio ou > 5000 caracteres         |

---

## Tasks

> Todos os endpoints exigem autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

Cada tarefa pertence a uma coluna (`status`) e possui um `order` inteiro que determina a posição na coluna do Kanban. A reordenação é atômica: ao mover ou alterar o `status`, o backend renumera as tarefas afetadas em uma única transação para manter a sequência sem buracos.

- Status disponíveis: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`
- Prioridades disponíveis: `LOW`, `MEDIUM`, `HIGH`
- O campo `completed_at` é preenchido automaticamente quando o status passa para `DONE` e limpo quando sai de `DONE`
- Alterar o `assigned_to` (na criação ou em atualização) dispara a notificação `TASK_ASSIGNED` ao novo responsável (respeita preferência de notificação do usuário — ver seção [Notifications](#notifications))

---

### `POST /api/v1/tasks`

Cria uma nova tarefa. A tarefa pode ser vinculada a um cliente, a um processo ou ficar avulsa.

**Body**

```json
{
  "title": "Revisar contrato de prestação de serviços",
  "description": "Conferir cláusulas 4 e 7 antes da assinatura.",
  "due_date": "2026-05-30T17:00:00Z",
  "priority": "HIGH",
  "assigned_to": 5,
  "client_id": 7,
  "process_id": 12
}
```

> Apenas `title` é obrigatório. `priority` default é `MEDIUM`. `status` inicial é sempre `TODO`. O `order` é atribuído automaticamente como o próximo valor disponível na coluna `TODO`.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Revisar contrato de prestação de serviços",
    "description": "Conferir cláusulas 4 e 7 antes da assinatura.",
    "due_date": "2026-05-30T17:00:00Z",
    "priority": "HIGH",
    "status": "TODO",
    "order": 0,
    "assigned_to": 5,
    "assigned_to_name": "Ana Lima",
    "client_id": 7,
    "process_id": 12,
    "created_by": 3,
    "created_by_name": "Carlos Souza",
    "updated_by": 3,
    "completed_at": null,
    "created_at": "2026-05-19T12:00:00Z",
    "updated_at": "2026-05-19T12:00:00Z"
  }
}
```

**Erros**

| Status | Code                   | Situação                                              |
| ------ | ---------------------- | ----------------------------------------------------- |
| 401    | `UNAUTHORIZED`         | Token ausente ou inválido                             |
| 422    | `ASSIGNEE_NOT_FOUND`   | `assigned_to` informado não existe                    |
| 422    | `TASK_CLIENT_NOT_FOUND`| `client_id` informado não existe                      |
| 422    | `TASK_PROCESS_NOT_FOUND`| `process_id` informado não existe                    |
| 422    | `VALIDATION_ERROR`     | `title` ausente, vazio ou > 150 caracteres            |

---

### `GET /api/v1/tasks`

Lista tarefas com filtros e paginação. Ordenado por `status, order, id` para suportar a renderização direta de um quadro Kanban.

**Query params**

| Parâmetro        | Tipo                                                | Obrigatório | Descrição                                            |
| ---------------- | --------------------------------------------------- | ----------- | ---------------------------------------------------- |
| `assigned_to`    | `integer`                                           | Não         | Filtra por responsável                               |
| `status`         | `TODO` \| `IN_PROGRESS` \| `BLOCKED` \| `DONE`      | Não         | Filtra por coluna do Kanban                          |
| `priority`       | `LOW` \| `MEDIUM` \| `HIGH`                         | Não         | Filtra por prioridade                                |
| `client_id`      | `integer`                                           | Não         | Filtra por cliente vinculado                         |
| `process_id`     | `integer`                                           | Não         | Filtra por processo vinculado                        |
| `due_date_from`  | `datetime` ISO 8601                                 | Não         | Limite inferior (inclusive) para `due_date`          |
| `due_date_to`    | `datetime` ISO 8601                                 | Não         | Limite superior (inclusive) para `due_date`          |
| `page`           | `integer` (≥ 1)                                     | Não         | Página atual (default: `1`)                          |
| `limit`          | `integer` (1–100)                                   | Não         | Itens por página (default: `20`)                     |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "title": "Revisar contrato de prestação de serviços",
      "description": "Conferir cláusulas 4 e 7 antes da assinatura.",
      "due_date": "2026-05-30T17:00:00Z",
      "priority": "HIGH",
      "status": "TODO",
      "order": 0,
      "assigned_to": 5,
      "assigned_to_name": "Ana Lima",
      "client_id": 7,
      "process_id": 12,
      "created_by": 3,
      "created_by_name": "Carlos Souza",
      "updated_by": 3,
      "completed_at": null,
      "created_at": "2026-05-19T12:00:00Z",
      "updated_at": "2026-05-19T12:00:00Z"
    }
  ],
  "meta": {
    "total": 1,
    "page": 1,
    "limit": 20,
    "pages": 1
  }
}
```

---

### `GET /api/v1/tasks/kanban`

Retorna as tarefas agrupadas pelas 4 colunas do Kanban (`TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`), ordenadas por `order ASC` dentro de cada coluna. As 4 chaves são **sempre** retornadas, mesmo que vazias — assim o front-end pode renderizar todas as colunas sem precisar inferir nomes.

Cada coluna é truncada em `KANBAN_MAX_PER_COLUMN` itens (default `100`, configurável via env). Quando uma coluna tem mais tarefas que o limite, `has_more=true` e o front-end deve buscar o restante via `GET /api/v1/tasks?status=...&page=N` com paginação tradicional.

**Query params**

| Parâmetro     | Tipo      | Obrigatório | Descrição                     |
| ------------- | --------- | ----------- | ----------------------------- |
| `assigned_to` | `integer` | Não         | Filtra por responsável        |
| `client_id`   | `integer` | Não         | Filtra por cliente vinculado  |
| `process_id`  | `integer` | Não         | Filtra por processo vinculado |

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "TODO": {
      "items": [
        {
          "id": 1,
          "title": "Revisar contrato",
          "description": null,
          "due_date": null,
          "priority": "MEDIUM",
          "status": "TODO",
          "order": 0,
          "assigned_to": 5,
          "assigned_to_name": "Ana Lima",
          "client_id": null,
          "process_id": null,
          "created_by": 3,
          "created_by_name": "Carlos Souza",
          "updated_by": 3,
          "completed_at": null,
          "created_at": "2026-05-19T12:00:00Z",
          "updated_at": "2026-05-19T12:00:00Z"
        }
      ],
      "total": 1,
      "has_more": false
    },
    "IN_PROGRESS": { "items": [], "total": 0, "has_more": false },
    "BLOCKED": { "items": [], "total": 0, "has_more": false },
    "DONE": { "items": [], "total": 0, "has_more": false }
  }
}
```

> `total` é o número real de tarefas na coluna (antes do truncamento), útil para exibir o contador na header da coluna. `has_more` é `true` quando `total > KANBAN_MAX_PER_COLUMN`.

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `GET /api/v1/tasks/{task_id}`

Retorna os dados completos de uma tarefa.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Revisar contrato de prestação de serviços",
    "description": "Conferir cláusulas 4 e 7 antes da assinatura.",
    "due_date": "2026-05-30T17:00:00Z",
    "priority": "HIGH",
    "status": "TODO",
    "order": 0,
    "assigned_to": 5,
    "assigned_to_name": "Ana Lima",
    "client_id": 7,
    "process_id": 12,
    "created_by": 3,
    "created_by_name": "Carlos Souza",
    "updated_by": 3,
    "completed_at": null,
    "created_at": "2026-05-19T12:00:00Z",
    "updated_at": "2026-05-19T12:00:00Z"
  }
}
```

**Erros**

| Status | Code              | Situação                  |
| ------ | ----------------- | ------------------------- |
| 401    | `UNAUTHORIZED`    | Token ausente ou inválido |
| 404    | `TASK_NOT_FOUND`  | Tarefa não encontrada     |

---

### `PATCH /api/v1/tasks/{task_id}`

Atualização parcial. Aceita qualquer subconjunto dos campos editáveis (`title`, `description`, `due_date`, `priority`, `status`, `assigned_to`, `client_id`, `process_id`).

> Para reposicionar a tarefa dentro de uma coluna ou movê-la entre colunas com `order` explícito, prefira o endpoint dedicado [`PATCH /api/v1/tasks/{task_id}/move`](#patch-apiv1taskstask_idmove).

Comportamentos especiais:

- Alterar `status` via este endpoint move a tarefa para o **fim** da nova coluna e renumera a coluna de origem; `completed_at` é ajustado automaticamente quando o destino é `DONE`.
- Alterar `assigned_to` para um novo responsável dispara a notificação `TASK_ASSIGNED`.
- Campos não enviados permanecem inalterados. Campos extras são rejeitados (`extra="forbid"`).

**Body (exemplo)**

```json
{
  "title": "Revisar contrato — urgência aumentada",
  "priority": "HIGH",
  "assigned_to": 8
}
```

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Revisar contrato — urgência aumentada",
    "description": "Conferir cláusulas 4 e 7 antes da assinatura.",
    "due_date": "2026-05-30T17:00:00Z",
    "priority": "HIGH",
    "status": "TODO",
    "order": 0,
    "assigned_to": 8,
    "assigned_to_name": "Marcos Diniz",
    "client_id": 7,
    "process_id": 12,
    "created_by": 3,
    "created_by_name": "Carlos Souza",
    "updated_by": 3,
    "completed_at": null,
    "created_at": "2026-05-19T12:00:00Z",
    "updated_at": "2026-05-19T13:10:00Z"
  }
}
```

**Erros**

| Status | Code                     | Situação                                              |
| ------ | ------------------------ | ----------------------------------------------------- |
| 401    | `UNAUTHORIZED`           | Token ausente ou inválido                             |
| 404    | `TASK_NOT_FOUND`         | Tarefa não encontrada                                 |
| 422    | `ASSIGNEE_NOT_FOUND`     | `assigned_to` informado não existe                    |
| 422    | `TASK_CLIENT_NOT_FOUND`  | `client_id` informado não existe                      |
| 422    | `TASK_PROCESS_NOT_FOUND` | `process_id` informado não existe                     |
| 422    | `VALIDATION_ERROR`       | Body inválido, campo desconhecido ou valor fora dos limites |

---

### `PATCH /api/v1/tasks/{task_id}/move`

Move uma tarefa para um destino específico no Kanban, informando `status` (coluna) e `order` (posição). A reordenação das tarefas afetadas — na coluna de origem e na de destino — acontece em uma única transação.

Regras de reordenação:

- **Mesma coluna (`status` igual ao atual)**: as demais tarefas entre a posição antiga e a nova são deslocadas para preencher o intervalo, sem buracos.
- **Coluna diferente**: a coluna de origem é renumerada (tarefas com `order` maior que o antigo são decrementadas) e a coluna de destino abre espaço a partir do `order` informado (tarefas com `order` ≥ ao novo são incrementadas).
- Se o `order` informado exceder o tamanho da coluna de destino, é truncado para o final da coluna.
- Mover para `DONE` preenche `completed_at` automaticamente; mover de `DONE` para qualquer outro status limpa o campo.

**Body**

```json
{
  "status": "IN_PROGRESS",
  "order": 0
}
```

> `status` deve ser um valor válido do enum `TaskStatus`. `order` deve ser ≥ 0.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Revisar contrato de prestação de serviços",
    "description": "Conferir cláusulas 4 e 7 antes da assinatura.",
    "due_date": "2026-05-30T17:00:00Z",
    "priority": "HIGH",
    "status": "IN_PROGRESS",
    "order": 0,
    "assigned_to": 5,
    "assigned_to_name": "Ana Lima",
    "client_id": 7,
    "process_id": 12,
    "created_by": 3,
    "created_by_name": "Carlos Souza",
    "updated_by": 3,
    "completed_at": null,
    "created_at": "2026-05-19T12:00:00Z",
    "updated_at": "2026-05-19T14:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                                           |
| ------ | ------------------ | -------------------------------------------------- |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido                          |
| 404    | `TASK_NOT_FOUND`   | Tarefa não encontrada                              |
| 422    | `VALIDATION_ERROR` | `status` inválido ou `order` negativo              |

---

### `DELETE /api/v1/tasks/{task_id}`

Remove uma tarefa e renumera a coluna em que ela estava para manter a sequência sem buracos.

> Somente o **criador** da tarefa (`created_by`) ou um usuário com role `ADMIN` pode excluir.

**Resposta 204**

Sem corpo.

**Erros**

| Status | Code             | Situação                                                  |
| ------ | ---------------- | --------------------------------------------------------- |
| 401    | `UNAUTHORIZED`   | Token ausente ou inválido                                 |
| 403    | `FORBIDDEN`      | Usuário não é o criador nem ADMIN                         |
| 404    | `TASK_NOT_FOUND` | Tarefa não encontrada                                     |

---

## Forensic Holidays

> `GET` exige autenticação (qualquer role). `POST/PATCH/DELETE` exigem role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

Tabela de feriados forenses usada pelo módulo `deadlines` no cálculo de prazos. Cada feriado tem um `scope`:

- `NATIONAL` — vale para todos (`court`/`comarca` devem ser `null`)
- `COURT` — vale para um tribunal específico (`court` obrigatório, `comarca` deve ser `null`)
- `COMARCA` — vale para uma comarca específica (`comarca` obrigatório)

Seed inicial: `python -m app.modules.forensic_holidays.seed [ano ...]` cobre feriados nacionais (Lei 10.406), recesso forense (art. 220 CPC, 20/12–20/01) e feriados TJDFT do ano corrente e do próximo. Operação idempotente.

---

### `GET /api/v1/forensic-holidays`

Lista feriados com filtros opcionais. Quando `court` ou `comarca` são informados, a query retorna **NATIONAL + COURT correspondente + COMARCA correspondente** (união). Sem filtros, retorna todos.

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                                       |
| --------- | ----------------- | ----------- | ----------------------------------------------- |
| `year`    | `integer`         | Não         | Filtra por ano (`YYYY-01-01` a `YYYY-12-31`)    |
| `court`   | `string`          | Não         | Inclui feriados COURT desse tribunal            |
| `comarca` | `string`          | Não         | Inclui feriados COMARCA dessa comarca           |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)                     |
| `limit`   | `integer` (1–500) | Não         | Itens por página (default: `100`)               |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "date": "2026-05-01",
      "description": "Dia do Trabalho",
      "scope": "NATIONAL",
      "court": null,
      "comarca": null,
      "created_at": "2026-05-19T12:00:00Z",
      "updated_at": "2026-05-19T12:00:00Z"
    }
  ],
  "meta": { "total": 1, "page": 1, "limit": 100, "pages": 1 }
}
```

---

### `POST /api/v1/forensic-holidays`

Cria um novo feriado. Admin only.

**Body**

```json
{
  "date": "2026-04-23",
  "description": "Aniversário de Brasília (TJDFT)",
  "scope": "COURT",
  "court": "TJDFT"
}
```

**Resposta 201** — mesmo formato do GET.

**Erros**

| Status | Code                          | Situação                                                                                |
| ------ | ----------------------------- | --------------------------------------------------------------------------------------- |
| 401    | `UNAUTHORIZED`                | Token ausente ou inválido                                                               |
| 403    | `FORBIDDEN`                   | Usuário não é ADMIN                                                                     |
| 422    | `INVALID_HOLIDAY_SCOPE`       | Combinação inválida de `scope`/`court`/`comarca`                                        |
| 422    | `VALIDATION_ERROR`            | Body inválido                                                                           |

---

### `PATCH /api/v1/forensic-holidays/{holiday_id}`

Atualiza parcialmente um feriado. Admin only. Para limpar `court`/`comarca`, enviar `null` explicitamente.

**Erros**

| Status | Code                          | Situação                                  |
| ------ | ----------------------------- | ----------------------------------------- |
| 401    | `UNAUTHORIZED`                | Token ausente ou inválido                 |
| 403    | `FORBIDDEN`                   | Usuário não é ADMIN                       |
| 404    | `FORENSIC_HOLIDAY_NOT_FOUND`  | Feriado não encontrado                    |
| 422    | `INVALID_HOLIDAY_SCOPE`       | Estado resultante viola regras de scope   |

---

### `DELETE /api/v1/forensic-holidays/{holiday_id}`

Remove um feriado. Admin only. Retorna 204 sem corpo.

---

## Deadlines

> Todos os endpoints exigem autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

Calcula e persiste prazos processuais em dias úteis, pulando finais de semana e feriados aplicáveis (NATIONAL + COURT do processo + COMARCA do prazo). O `court` é snapshot do `Process` no momento da criação; `comarca` é snapshot do que foi enviado no body. Mudanças futuras em `Process` não afetam prazos antigos.

Algoritmo:
1. Se `start_date` cai em dia não-útil, avança até o próximo dia útil (sem contar).
2. Conta `business_days` dias úteis, pulando sábados, domingos e feriados aplicáveis.
3. Retorna a data final + a lista de dias pulados (útil para a UI explicar o cálculo).

---

### `POST /api/v1/deadlines/calculate`

Calcula a data-limite sem persistir nada. Útil para preview no formulário.

**Body**

```json
{
  "start_date": "2026-05-11",
  "business_days": 15,
  "court": "TJDFT",
  "comarca": "Brasília"
}
```

> `court` e `comarca` são opcionais. Sem eles, apenas feriados `NATIONAL` são considerados.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "start_date": "2026-05-11",
    "business_days": 15,
    "due_date": "2026-06-01",
    "court": "TJDFT",
    "comarca": "Brasília",
    "skipped_days": [
      { "date": "2026-05-16", "reason": "WEEKEND", "description": null },
      { "date": "2026-05-17", "reason": "WEEKEND", "description": null }
    ]
  }
}
```

> `reason`: `"WEEKEND"` ou `"HOLIDAY"`. Para feriados, `description` contém o nome do feriado.

**Erros**

| Status | Code                      | Situação                              |
| ------ | ------------------------- | ------------------------------------- |
| 401    | `UNAUTHORIZED`            | Token ausente ou inválido             |
| 422    | `INVALID_DEADLINE_RANGE`  | `business_days` ≤ 0                   |
| 422    | `VALIDATION_ERROR`        | Body inválido                         |

---

### `POST /api/v1/processes/{process_id}/deadlines`

Cria prazo persistido vinculado a um processo. Calcula `due_date` automaticamente usando o `court` do Process e o `comarca` do body (opcional).

**Body**

```json
{
  "start_date": "2026-05-11",
  "business_days": 15,
  "deadline_type": "Contestação",
  "comarca": "Brasília"
}
```

> `deadline_type` é string livre (até 120 chars), ex: "Contestação", "Réplica", "Recurso".

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "process_id": 12,
    "start_date": "2026-05-11",
    "business_days": 15,
    "deadline_type": "Contestação",
    "due_date": "2026-06-01",
    "court": "TJDFT",
    "comarca": "Brasília",
    "created_by": 3,
    "created_at": "2026-05-19T12:00:00Z",
    "updated_at": "2026-05-19T12:00:00Z"
  }
}
```

**Erros**

| Status | Code                     | Situação                                |
| ------ | ------------------------ | --------------------------------------- |
| 401    | `UNAUTHORIZED`           | Token ausente ou inválido               |
| 404    | `PROCESS_NOT_FOUND`      | Processo não encontrado                 |
| 422    | `INVALID_DEADLINE_RANGE` | `business_days` ≤ 0                     |
| 422    | `VALIDATION_ERROR`       | Body inválido                           |

---

### `GET /api/v1/processes/{process_id}/deadlines`

Lista prazos do processo, ordenados por `due_date ASC, id ASC`, com paginação.

**Query params**

| Parâmetro | Tipo              | Obrigatório | Descrição                        |
| --------- | ----------------- | ----------- | -------------------------------- |
| `page`    | `integer` (≥ 1)   | Não         | Página atual (default: `1`)      |
| `limit`   | `integer` (1–100) | Não         | Itens por página (default: `20`) |

**Erros**

| Status | Code                | Situação                  |
| ------ | ------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`      | Token ausente ou inválido |
| 404    | `PROCESS_NOT_FOUND` | Processo não encontrado   |

---

### `PATCH /api/v1/deadlines/{deadline_id}`

Atualiza um prazo. Se `start_date`, `business_days` ou `comarca` mudarem, o `due_date` é **recalculado automaticamente** usando o `court` já snapshotado. Para alterar só metadado (`deadline_type`), envie apenas esse campo.

**Body** (todos opcionais)

```json
{
  "start_date": "2026-05-12",
  "business_days": 20,
  "deadline_type": "Recurso",
  "comarca": null
}
```

**Erros**

| Status | Code                     | Situação                  |
| ------ | ------------------------ | ------------------------- |
| 401    | `UNAUTHORIZED`           | Token ausente ou inválido |
| 404    | `DEADLINE_NOT_FOUND`     | Prazo não encontrado      |
| 422    | `INVALID_DEADLINE_RANGE` | `business_days` ≤ 0       |
| 422    | `VALIDATION_ERROR`       | Body inválido             |

---

### `DELETE /api/v1/deadlines/{deadline_id}`

Remove um prazo. Retorna 204 sem corpo.

**Erros**

| Status | Code                 | Situação                  |
| ------ | -------------------- | ------------------------- |
| 401    | `UNAUTHORIZED`       | Token ausente ou inválido |
| 404    | `DEADLINE_NOT_FOUND` | Prazo não encontrado      |

---

## Alertas de prazo

Um job cron diário (APScheduler) varre os prazos e dispara alertas por e-mail em intervalos escalonados, contados em **dias úteis** até a data-limite. Configurável por variáveis de ambiente:

| Variável                  | Default          | Descrição                                          |
| ------------------------- | ---------------- | -------------------------------------------------- |
| `SCHEDULER_ENABLED`       | `true`           | Liga/desliga o scheduler                           |
| `DEADLINE_ALERT_CRON`     | `06:00`          | Horário diário do job, formato `HH:MM` (fuso local) |
| `DEADLINE_ALERT_INTERVALS`| `30,15,7,3,2,1`  | Intervalos de alerta, em dias úteis                |
| `DATAJUD_SYNC_INTERVAL_HOURS` | `6`          | Intervalo do job recorrente de sync DataJud        |
| `DATAJUD_SYNC_LIMIT`      | `50`             | Máximo de processos ativos por ciclo DataJud       |
| `DATAJUD_SYNC_USER_ID`    | `null`           | Usuário registrado como autor do sync agendado     |

Regras de disparo:

- Prazos **não-vencidos**: quando os dias úteis restantes entram numa janela configurada, dispara `DEADLINE_APPROACHING`. Para um prazo criado já dentro de uma janela, o job dispara no ciclo seguinte o alerta da menor janela aplicável (um único e-mail).
- Prazos **vencidos** (`due_date < hoje`): dispara `DEADLINE_EXPIRED` uma única vez.
- Cada par (prazo, intervalo) gera no máximo um alerta — registrado na tabela `deadline_alert`.
- O destinatário é o `created_by` do prazo. Respeita a preferência de notificação do usuário (US-22).

---

### `GET /api/v1/processes/{process_id}/deadlines/{deadline_id}/alerts`

Lista o histórico de alertas já disparados para um prazo. Acessível apenas ao autor do prazo (`created_by`) ou a usuários com role `ADMIN`.

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 1,
      "deadline_id": 12,
      "days_before": 15,
      "kind": "APPROACHING",
      "sent_at": "2026-05-19T06:00:03Z"
    },
    {
      "id": 2,
      "deadline_id": 12,
      "days_before": -1,
      "kind": "EXPIRED",
      "sent_at": "2026-06-10T06:00:01Z"
    }
  ]
}
```

> `kind`: `"APPROACHING"` (alerta de proximidade — `days_before` é o intervalo em dias úteis) ou `"EXPIRED"` (alerta de prazo vencido — `days_before` é o sentinela `-1`).

**Erros**

| Status | Code                 | Situação                                            |
| ------ | -------------------- | --------------------------------------------------- |
| 401    | `UNAUTHORIZED`       | Token ausente ou inválido                           |
| 403    | `FORBIDDEN`          | Usuário não é o autor do prazo nem ADMIN            |
| 404    | `PROCESS_NOT_FOUND`  | Processo não encontrado                             |
| 404    | `DEADLINE_NOT_FOUND` | Prazo não encontrado ou não pertence ao processo    |

---

## Appointments

> Todos os endpoints exigem autenticação (qualquer role).
> Header obrigatório: `Authorization: Bearer <token>`

Agenda pessoal de compromissos. Cada compromisso pertence ao usuário que o criou (`created_by`). O dono acessa os seus; usuários com role `ADMIN` podem ver/editar/excluir qualquer compromisso. A listagem retorna apenas os compromissos do usuário autenticado.

Datas são armazenadas em UTC. `type`: `AUDIENCIA` | `REUNIAO` | `PRAZO` | `OUTRO`. Os campos `google_event_id` e `is_synced_to_google` pertencem à integração com o Google Calendar (fase 2) e hoje vêm sempre `null`/`false`.

---

### `POST /api/v1/appointments`

Cria um compromisso. O autor é o usuário autenticado.

**Body**

```json
{
  "title": "Audiência de conciliação",
  "type": "AUDIENCIA",
  "starts_at": "2026-12-01T14:00:00Z",
  "duration_minutes": 60,
  "client_id": 7,
  "process_id": 12,
  "description": "Levar procuração atualizada.",
  "location": "Fórum Central, sala 3"
}
```

> Obrigatórios: `title`, `type`, `starts_at`, `duration_minutes`. `client_id`, `process_id`, `description`, `location` são opcionais. `starts_at` não pode estar no passado. `duration_minutes` entre 1 e 1440.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "title": "Audiência de conciliação",
    "type": "AUDIENCIA",
    "starts_at": "2026-12-01T14:00:00Z",
    "duration_minutes": 60,
    "description": "Levar procuração atualizada.",
    "location": "Fórum Central, sala 3",
    "client_id": 7,
    "process_id": 12,
    "created_by": 3,
    "created_by_name": "Ana Lima",
    "google_event_id": null,
    "is_synced_to_google": false,
    "created_at": "2026-05-20T12:00:00Z",
    "updated_at": "2026-05-20T12:00:00Z"
  }
}
```

**Erros**

| Status | Code                            | Situação                                      |
| ------ | ------------------------------- | --------------------------------------------- |
| 401    | `UNAUTHORIZED`                  | Token ausente ou inválido                     |
| 422    | `APPOINTMENT_CLIENT_NOT_FOUND`  | `client_id` informado não existe              |
| 422    | `APPOINTMENT_PROCESS_NOT_FOUND` | `process_id` informado não existe             |
| 422    | `VALIDATION_ERROR`              | Body inválido ou `starts_at` no passado       |

---

### `GET /api/v1/appointments`

Lista os compromissos do usuário autenticado, ordenados por `starts_at` ascendente, com filtros e paginação.

**Query params**

| Parâmetro    | Tipo                                                  | Obrigatório | Descrição                          |
| ------------ | ----------------------------------------------------- | ----------- | ---------------------------------- |
| `date_from`  | `datetime` (ISO 8601)                                 | Não         | Filtra `starts_at >= date_from`    |
| `date_to`    | `datetime` (ISO 8601)                                 | Não         | Filtra `starts_at <= date_to`      |
| `type`       | `AUDIENCIA` \| `REUNIAO` \| `PRAZO` \| `OUTRO`        | Não         | Filtra por tipo                    |
| `client_id`  | `integer`                                             | Não         | Filtra por cliente vinculado       |
| `process_id` | `integer`                                             | Não         | Filtra por processo vinculado      |
| `page`       | `integer` (≥ 1)                                       | Não         | Página atual (default: `1`)        |
| `limit`      | `integer` (1–100)                                     | Não         | Itens por página (default: `20`)   |

**Resposta 200** — mesmo formato de item de `POST`, dentro de `PaginatedResponse`.

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `GET /api/v1/appointments/{appointment_id}`

Retorna os detalhes de um compromisso. Acessível ao dono ou a um `ADMIN`.

**Erros**

| Status | Code                    | Situação                              |
| ------ | ----------------------- | ------------------------------------- |
| 401    | `UNAUTHORIZED`          | Token ausente ou inválido             |
| 403    | `FORBIDDEN`             | Usuário não é o dono nem ADMIN        |
| 404    | `APPOINTMENT_NOT_FOUND` | Compromisso não encontrado            |

---

### `PATCH /api/v1/appointments/{appointment_id}`

Atualiza parcialmente um compromisso. Todos os campos são opcionais. Diferente da criação, `starts_at` pode estar no passado (correção de registro). Acessível ao dono ou a um `ADMIN`.

**Erros**

| Status | Code                            | Situação                          |
| ------ | ------------------------------- | --------------------------------- |
| 401    | `UNAUTHORIZED`                  | Token ausente ou inválido         |
| 403    | `FORBIDDEN`                     | Usuário não é o dono nem ADMIN    |
| 404    | `APPOINTMENT_NOT_FOUND`         | Compromisso não encontrado        |
| 422    | `APPOINTMENT_CLIENT_NOT_FOUND`  | `client_id` informado não existe  |
| 422    | `APPOINTMENT_PROCESS_NOT_FOUND` | `process_id` informado não existe |
| 422    | `VALIDATION_ERROR`              | Body inválido                     |

---

### `DELETE /api/v1/appointments/{appointment_id}`

Remove um compromisso. Acessível ao dono ou a um `ADMIN`. Retorna 204 sem corpo.

**Erros**

| Status | Code                    | Situação                       |
| ------ | ----------------------- | ------------------------------ |
| 401    | `UNAUTHORIZED`          | Token ausente ou inválido      |
| 403    | `FORBIDDEN`             | Usuário não é o dono nem ADMIN |
| 404    | `APPOINTMENT_NOT_FOUND` | Compromisso não encontrado     |

---

## Google Calendar (integração)

> Os endpoints `auth-url`, `status` e `DELETE` exigem autenticação. O `callback` é aberto pelo browser via redirect do Google e não usa header de autenticação — ele identifica o usuário por um `state` assinado.

Integração **opcional** e **unidirecional** (sistema → Google). Quando um usuário conecta sua conta, criar/editar/excluir um compromisso reflete a operação no Google Calendar dele. Falha no Google nunca bloqueia a operação local — é apenas logada. Mudanças feitas direto no Google **não** voltam para o sistema. Ver setup no [README](../README.md).

Se o servidor não tiver as variáveis `GOOGLE_*` configuradas, `auth-url` responde 503 `GOOGLE_NOT_CONFIGURED` e `status` responde `connected: false`.

---

### `GET /api/v1/integrations/google/auth-url`

Retorna a URL de consentimento OAuth do Google para o usuário iniciar a conexão.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "auth_url": "https://accounts.google.com/o/oauth2/auth?..."
  }
}
```

**Erros**

| Status | Code                   | Situação                                |
| ------ | ---------------------- | --------------------------------------- |
| 401    | `UNAUTHORIZED`         | Token ausente ou inválido               |
| 503    | `GOOGLE_NOT_CONFIGURED`| Integração não configurada no servidor  |

---

### `GET /api/v1/integrations/google/callback`

Callback do OAuth. O Google redireciona o browser para cá com `code` e `state`. O endpoint troca o `code` por tokens, persiste o `refresh_token` criptografado e redireciona (302) para o frontend.

**Query params:** `code`, `state`, `error` (todos enviados pelo Google).

**Resposta 302** — redirect para `{FRONTEND_URL}/?google_calendar=connected` em caso de sucesso, ou `?google_calendar=error` em qualquer falha (usuário negou, `state` inválido/expirado, erro na troca do code).

---

### `GET /api/v1/integrations/google/status`

Indica se o usuário autenticado tem o Google Calendar conectado.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "connected": true,
    "connected_at": "2026-05-20T12:00:00Z",
    "scope": "https://www.googleapis.com/auth/calendar.events"
  }
}
```

> Quando não conectado: `connected: false`, `connected_at: null`, `scope: null`.

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `DELETE /api/v1/integrations/google`

Desconecta o Google Calendar do usuário — remove a credencial local. Idempotente (retorna 204 mesmo se já não havia conexão). Eventos já sincronizados permanecem no Google Calendar do usuário.

**Resposta 204** — sem corpo.

**Erros**

| Status | Code           | Situação                  |
| ------ | -------------- | ------------------------- |
| 401    | `UNAUTHORIZED` | Token ausente ou inválido |

---

### `POST /api/v1/integrations/google/sync-all`

Sincronização retroativa: envia ao Google Calendar os compromissos **futuros** do usuário que ainda não foram sincronizados (`is_synced_to_google = false`). Útil logo após conectar a conta, já que conectar não empurra o histórico automaticamente.

É **idempotente** — só varre os não-sincronizados, então rodar de novo não recria eventos. Compromissos no passado são ignorados. Falha pontual no Google é contabilizada em `failed` e não interrompe os demais.

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "total": 5,
    "synced": 5,
    "failed": 0
  }
}
```

> `total` = compromissos elegíveis varridos; `synced` = enviados com sucesso; `failed` = falharam no Google (continuam com `is_synced_to_google = false`).

**Erros**

| Status | Code                    | Situação                                       |
| ------ | ----------------------- | ---------------------------------------------- |
| 401    | `UNAUTHORIZED`          | Token ausente ou inválido                      |
| 409    | `GOOGLE_NOT_CONNECTED`  | Usuário não conectou uma conta Google          |
| 503    | `GOOGLE_NOT_CONFIGURED` | Integração não configurada no servidor         |

---

## Finance

> Todos os endpoints exigem role `ADMIN`.
> Header obrigatório: `Authorization: Bearer <token>`

Lançamentos financeiros do escritório. Entradas (`INCOME`) e saídas (`EXPENSE`) ficam na mesma tabela, diferenciadas por `type`.

- `amount` é decimal positivo com até 2 casas e é **retornado como string** (ex.: `"1500.50"`) para não perder precisão
- `transaction_date` é a data do lançamento (`YYYY-MM-DD`) e é a data usada nos filtros por período

---

### `POST /api/v1/finance/incomes`

Registra uma entrada financeira.

**Body**

```json
{
  "description": "Honorários contratuais",
  "amount": "1500.50",
  "transaction_date": "2026-09-01"
}
```

> `amount` aceita número ou string; deve ser > 0 e ter no máximo 2 casas decimais.

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 1,
    "type": "INCOME",
    "description": "Honorários contratuais",
    "amount": "1500.50",
    "transaction_date": "2026-09-01",
    "created_by": 3,
    "created_at": "2026-09-13T12:00:00Z",
    "updated_at": "2026-09-13T12:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                                                                 |
| ------ | ------------------ | ------------------------------------------------------------------------ |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido                                                |
| 403    | `FORBIDDEN`        | Usuário não é `ADMIN`                                                    |
| 422    | `VALIDATION_ERROR` | `description` vazia, `amount` ≤ 0 ou com mais de 2 casas, data inválida  |

---

### `POST /api/v1/finance/expenses`

Registra uma saída financeira. Mesmo body e mesmas validações de `POST /api/v1/finance/incomes`.

**Body**

```json
{
  "description": "Aluguel do escritório",
  "amount": "3200.00",
  "transaction_date": "2026-09-05"
}
```

**Resposta 201**

```json
{
  "success": true,
  "data": {
    "id": 2,
    "type": "EXPENSE",
    "description": "Aluguel do escritório",
    "amount": "3200.00",
    "transaction_date": "2026-09-05",
    "created_by": 3,
    "created_at": "2026-09-13T12:00:00Z",
    "updated_at": "2026-09-13T12:00:00Z"
  }
}
```

**Erros**

| Status | Code               | Situação                                                                 |
| ------ | ------------------ | ------------------------------------------------------------------------ |
| 401    | `UNAUTHORIZED`     | Token ausente ou inválido                                                |
| 403    | `FORBIDDEN`        | Usuário não é `ADMIN`                                                    |
| 422    | `VALIDATION_ERROR` | `description` vazia, `amount` ≤ 0 ou com mais de 2 casas, data inválida  |

---

### `GET /api/v1/finance/transactions`

Lista entradas e saídas com paginação e filtro opcional por período, ordenadas por `transaction_date DESC, id DESC`. Alimenta a tela de controle financeiro.

**Query params**

| Parâmetro   | Tipo                  | Obrigatório | Descrição                                           |
| ----------- | --------------------- | ----------- | --------------------------------------------------- |
| `date_from` | `date` (`YYYY-MM-DD`) | Não         | Limite inferior (inclusive) para `transaction_date` |
| `date_to`   | `date` (`YYYY-MM-DD`) | Não         | Limite superior (inclusive) para `transaction_date` |
| `page`      | `integer` (≥ 1)       | Não         | Página atual (default: `1`)                         |
| `limit`     | `integer` (1–100)     | Não         | Itens por página (default: `20`)                    |

**Resposta 200**

```json
{
  "success": true,
  "data": [
    {
      "id": 2,
      "type": "EXPENSE",
      "description": "Aluguel do escritório",
      "amount": "3200.00",
      "transaction_date": "2026-09-05",
      "created_by": 3,
      "created_at": "2026-09-13T12:00:00Z",
      "updated_at": "2026-09-13T12:00:00Z"
    }
  ],
  "meta": { "total": 1, "page": 1, "limit": 20, "pages": 1 }
}
```

**Erros**

| Status | Code                       | Situação                          |
| ------ | -------------------------- | --------------------------------- |
| 401    | `UNAUTHORIZED`             | Token ausente ou inválido         |
| 403    | `FORBIDDEN`                | Usuário não é `ADMIN`             |
| 422    | `INVALID_FINANCIAL_PERIOD` | `date_from` posterior a `date_to` |
| 422    | `VALIDATION_ERROR`         | Data em formato inválido          |

---

### `GET /api/v1/finance/summary`

Resumo financeiro. Soma as entradas e as saídas (no período, se informado) e calcula o saldo (`total_income - total_expense`). Sem `date_from`/`date_to`, considera todos os lançamentos.

**Query params**

| Parâmetro   | Tipo                  | Obrigatório | Descrição                                           |
| ----------- | --------------------- | ----------- | --------------------------------------------------- |
| `date_from` | `date` (`YYYY-MM-DD`) | Não         | Limite inferior (inclusive) para `transaction_date` |
| `date_to`   | `date` (`YYYY-MM-DD`) | Não         | Limite superior (inclusive) para `transaction_date` |

**Resposta 200**

```json
{
  "success": true,
  "data": {
    "date_from": "2026-09-01",
    "date_to": "2026-09-30",
    "total_income": "1500.00",
    "total_expense": "200.25",
    "balance": "1299.75"
  }
}
```

> Valores monetários são strings com 2 casas. `balance` pode ser negativo (ex.: `"-150.50"`). Sem lançamentos no período, os três valores vêm como `"0.00"`.

**Erros**

| Status | Code                       | Situação                          |
| ------ | -------------------------- | --------------------------------- |
| 401    | `UNAUTHORIZED`             | Token ausente ou inválido         |
| 403    | `FORBIDDEN`                | Usuário não é `ADMIN`             |
| 422    | `INVALID_FINANCIAL_PERIOD` | `date_from` posterior a `date_to` |
| 422    | `VALIDATION_ERROR`         | Data em formato inválido          |

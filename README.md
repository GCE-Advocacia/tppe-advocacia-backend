# Backend

API base em FastAPI com organização MVC + Camadas e Postgres.

## Rodando localmente

```bash
cp .env.example .env
docker compose up -d db
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

O modo local precisa do Postgres disponível. O caminho mais simples é subir apenas o serviço `db` com `docker compose up -d db` antes de iniciar o `uvicorn`

## DataJud

A integração com a API pública do DataJud usa `DATAJUD_API_KEY` e `DATAJUD_BASE_URL` do `.env`. Para sincronização automática, o APScheduler registra um job recorrente configurado por `DATAJUD_SYNC_INTERVAL_HOURS` (default `6`) e `DATAJUD_SYNC_LIMIT` (default `50`).

Cada processo pode salvar `tribunal_alias` (ex.: `tjsp`). A sincronização manual fica em `POST /api/v1/processes/{process_id}/sync`; a sincronização em lote fica em `POST /api/v1/datajud/sync-active-processes` para admins. Movimentações importadas entram como `source = SYSTEM` e usam `external_id` para deduplicação.

Também existe o script agendável externo:

```bash
python scripts/sync_datajud_active_processes.py --limit 50
```

## Rodando com Docker

```bash
cp .env.example .env
docker compose up --build
```

Se as portas `8000` ou `5432` já estiverem em uso, ajuste `API_HOST_PORT` e `POSTGRES_PORT` no `.env` antes de subir os containers.

## Integração Google Calendar

A agenda (`/api/v1/appointments`) pode sincronizar compromissos com o Google
Calendar de cada usuário (sync unidirecional: sistema -> Google). A integração
é **opcional** — se as variáveis `GOOGLE_*` ficarem em branco, a agenda
funciona normalmente, só sem sincronizar.

### 1. Gerar a chave de criptografia

O `refresh_token` do Google é guardado criptografado. Gere uma chave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copie o valor para `GOOGLE_TOKEN_ENCRYPTION_KEY` no `.env`.

> Não troque essa chave depois de conectar usuários — as credenciais já
> salvas deixariam de poder ser descriptografadas.

### 2. Setup no Google Cloud Console

1. Acesse <https://console.cloud.google.com/> e **crie um projeto**.
2. Em **APIs & Services -> Library**, habilite a **Google Calendar API**.
3. Em **APIs & Services -> OAuth consent screen**:
   - Tipo de usuário: **External**.
   - Publishing status: **Testing** (limite de 100 usuários; suficiente
     para o MVP — verificação só é exigida em produção).
   - Em **Test users**, adicione o e-mail de cada usuário que vai conectar.
   - Scope necessário: `https://www.googleapis.com/auth/calendar.events`.
4. Em **APIs & Services -> Credentials -> Create Credentials -> OAuth client ID**:
   - Application type: **Web application**.
   - Em **Authorized redirect URIs**, adicione exatamente o valor de
     `GOOGLE_REDIRECT_URI` (padrão:
     `http://localhost:8000/api/v1/integrations/google/callback`).
5. Copie o **Client ID** e o **Client secret** gerados.

### 3. Preencher o `.env`

```
GOOGLE_CLIENT_ID=<client id>
GOOGLE_CLIENT_SECRET=<client secret>
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/integrations/google/callback
GOOGLE_TOKEN_ENCRYPTION_KEY=<chave Fernet do passo 1>
```

Reinicie a API. Cada usuário conecta sua conta chamando
`GET /api/v1/integrations/google/auth-url` e abrindo a URL retornada.

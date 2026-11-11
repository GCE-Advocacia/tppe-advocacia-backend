# Deploy

O sistema roda em serviços de nuvem gratuitos ([US21](https://gce-advocacia.github.io/tppe-advocacia-docs/gce/backlog/us21/)):

| Parte | Serviço | Observações |
|---|---|---|
| API (este repositório) | [Render](https://render.com) | Web Service a partir do `Dockerfile`, plano gratuito (512 MB, hiberna após ~15 min sem acesso) |
| Frontend | [Netlify](https://netlify.com) | Repositório `tppe-advocacia-frontend` |
| Banco de dados | [Neon](https://neon.com) | PostgreSQL |
| Imagens e logos | Neon Object Storage | Bucket com leitura pública |
| Documentos dos processos | Google Drive do escritório | Conectado pelo administrador na página de Processos ([US09](https://gce-advocacia.github.io/tppe-advocacia-docs/gce/backlog/us09/)) |
| E-mails | [Resend](https://resend.com) | Exige domínio verificado para enviar aos clientes |
| API acordada | GitHub Actions | `.github/workflows/keep-alive.yml` acessa `/api/v1/health` a cada 10 min |

As contas devem ficar no nome do escritório, com a equipe como convidada.

O guia de deploy em VPS da US20 continua no [anexo](#anexo--deploy-em-vps-hostinger-ubuntu-2204), mais abaixo.

---

## Nuvem — Índice

1. [Banco no Neon](#n1-banco-no-neon)
2. [Object Storage no Neon](#n2-object-storage-no-neon)
3. [API no Render](#n3-api-no-render)
4. [Variáveis de ambiente da API](#n4-variáveis-de-ambiente-da-api)
5. [Frontend no Netlify](#n5-frontend-no-netlify)
6. [Google Cloud (Drive e Calendar)](#n6-google-cloud-drive-e-calendar)
7. [Resend](#n7-resend)
8. [Keep alive](#n8-keep-alive)
9. [Primeiro acesso e verificação](#n9-primeiro-acesso-e-verificação)
10. [Ordem dos deploys e cuidados](#n10-ordem-dos-deploys-e-cuidados)

---

## N1. Banco no Neon

1. Crie um projeto no Neon (região `us-east-2`, a mesma do Object Storage).
2. Em **Connect**, copie a conexão **direta**: o host **sem** `-pooler`. As migrações do Alembic e o `psycopg` funcionam melhor fora do pooler, e com 1 worker sobram conexões.
3. A conexão `postgresql://<usuário>:<senha>@<host>/<banco>?sslmode=require` vira as variáveis `POSTGRES_*` e `PGSSLMODE=require` (seção [N4](#n4-variáveis-de-ambiente-da-api)).

As migrações rodam sozinhas a cada deploy: o `scripts/start.sh` executa `alembic upgrade head` antes do gunicorn.

## N2. Object Storage no Neon

1. No projeto do Neon, crie um bucket com acesso **`public_read`** (por exemplo, `uploads`). O nível de acesso se muda pelo Console ou pela API do Neon, não pelo S3.
2. Gere uma credencial de storage com os escopos `storage:read` e `storage:write`. **Ela só aparece uma vez**: guarde no gerenciador de senhas.
3. Anote:
   - o endpoint S3 da branch, que vai em `AWS_ENDPOINT_URL_S3`;
   - a URL pública do bucket, no formato `https://<branch-id>.storage.<região>.aws.neon.tech/<bucket>`, que vai em `MEDIA_PUBLIC_BASE_URL`.
4. Teste abrindo no navegador a URL de um arquivo qualquer enviado ao bucket.

O bucket recebe só imagens públicas (landing page, capas de artigos, logos e favicon). **Nunca** coloque documentos nele.

## N3. API no Render

1. **New → Web Service**, ligado a este repositório, branch `main`, runtime **Docker**.
2. Deixe o campo **Docker Command** vazio. O `CMD` do `Dockerfile` chama `scripts/start.sh`, que aplica as migrações e sobe o gunicorn com `WEB_CONCURRENCY` workers (o Render define 1) na porta `$PORT`.
3. **Health Check Path:** `/api/v1/health`.
4. Configure as variáveis de ambiente (seção [N4](#n4-variáveis-de-ambiente-da-api)) **antes** do primeiro deploy.
5. **Auto-Deploy:** ligado. Cada merge na `main` gera um deploy.

Observações:

- O Shell do Render é pago. Comandos administrativos, como criar o admin, rodam da sua máquina apontando para o Neon (seção [N9](#n9-primeiro-acesso-e-verificação)).
- O disco do Render é apagado a cada deploy, por isso nenhum arquivo fica nele em produção.
- O plano gratuito dá 750 horas por mês. Um serviço ligado 24/7 usa ~744, então ele deve ser o único serviço gratuito na conta.

## N4. Variáveis de ambiente da API

Configure em **Render → Environment**. As que não aparecem aqui usam o valor padrão de `app/config/settings.py`.

| Variável | Valor em produção | Observação |
|---|---|---|
| `APP_ENV` | `production` | Desliga o Swagger e ativa as validações de produção |
| `JWT_SECRET_KEY` | aleatório, 32+ caracteres | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `POSTGRES_HOST` | host direto do Neon (sem `-pooler`) | |
| `POSTGRES_PORT` | `5432` | |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | da conexão do Neon | |
| `PGSSLMODE` | `require` | Lida pelo driver do Postgres; o Neon exige SSL |
| `PGCHANNELBINDING` | `require` | Opcional |
| `FRONTEND_URL` | `https://<site>.netlify.app` | Sem `/` no final. Usada no CORS e nos redirecionamentos do Google |
| `MEDIA_BUCKET` | nome do bucket (ex.: `uploads`) | **Obrigatória em produção**: sem ela, a API não sobe |
| `MEDIA_PUBLIC_BASE_URL` | URL pública do bucket | Base das URLs das imagens |
| `AWS_ENDPOINT_URL_S3` | endpoint S3 do Neon | |
| `AWS_REGION` | `us-east-2` | |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | credencial de storage do Neon | |
| `DOCUMENT_STORAGE` | `drive` | **Obrigatória em produção**: sem ela, a API não sobe |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | credencial OAuth do Google Cloud | |
| `GOOGLE_TOKEN_ENCRYPTION_KEY` | chave Fernet | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Trocar a chave invalida as conexões já feitas |
| `GOOGLE_REDIRECT_URI` | `https://<api>.onrender.com/api/v1/integrations/google/callback` | Google Calendar. **Não deixe `localhost`** |
| `GOOGLE_DRIVE_REDIRECT_URI` | `https://<api>.onrender.com/api/v1/integrations/google-drive/callback` | Google Drive. **Não deixe `localhost`** |
| `RESEND_API_KEY` | chave do Resend | Obrigatória: a API não sobe sem ela |
| `RESEND_FROM_EMAIL` | `nao-responda@<domínio do escritório>` | Precisa ser de um domínio verificado no Resend |
| `SCHEDULER_ENABLED` | `true` | O agendador roda dentro da API (1 worker, então não duplica) |
| `DEADLINE_ALERT_CRON` | `09:00` | O servidor está em UTC: 09:00 UTC = 06:00 em Brasília. Vale também para os lembretes de pagamento |
| `DATAJUD_API_KEY` | chave do Datajud | Sincronização de movimentações |

## N5. Frontend no Netlify

1. **Add new site → Import an existing project**, ligado ao `tppe-advocacia-frontend`, branch `main`.
2. Build: `npm run build`; diretório publicado: `dist`.
3. Variável **`VITE_API_URL`** = `https://<api>.onrender.com/api/v1`. Ela é lida **no build**: depois de mudar, rode **Trigger deploy → Clear cache and deploy site**.
4. O `netlify.toml` do frontend já tem o redirect da SPA (`/* → /index.html`).

## N6. Google Cloud (Drive e Calendar)

No projeto do Google Cloud do escritório:

1. **APIs e serviços → Biblioteca:** ative a **Google Drive API** e a **Google Calendar API**.
2. **Tela de consentimento OAuth** (*Google Auth Platform*):
   - **Data access:** escopos `https://www.googleapis.com/auth/drive.file` e `https://www.googleapis.com/auth/calendar.events`;
   - **Audience:** publique o app (**In production**). Em modo de teste, o token expira em 7 dias e o Drive se desconecta toda semana. Sem verificação, aparece o aviso "app não verificado" ao conectar (**Avançado → continuar**).
3. **Clients:** crie (ou edite) a credencial **Web application** e adicione em **URIs de redirecionamento autorizados**:
   - `https://<api>.onrender.com/api/v1/integrations/google/callback`
   - `https://<api>.onrender.com/api/v1/integrations/google-drive/callback`
   - opcionalmente, as mesmas URLs com `http://localhost:8000`, para desenvolvimento.

   O valor precisa ser **idêntico** ao das variáveis `GOOGLE_*_REDIRECT_URI`. Se não for, o Google mostra `redirect_uri_mismatch`.

   **Origens JavaScript autorizadas** não são necessárias, porque o fluxo OAuth é feito pelo servidor.
4. O **Client Secret** só aparece na criação: copie direto para o Render.

## N7. Resend

1. Crie a conta e adicione o **domínio do escritório**.
2. Cadastre no DNS do domínio os registros que o Resend mostrar e espere a verificação.
3. Crie uma API key e configure `RESEND_API_KEY` e `RESEND_FROM_EMAIL` no Render.

Sem domínio verificado, o Resend só entrega e-mails para o dono da conta, e os clientes não recebem alertas nem lembretes.

## N8. Keep alive

O workflow `.github/workflows/keep-alive.yml` acessa `/api/v1/health` a cada 10 minutos para a API não hibernar. Com ela acordada, o agendador interno roda os alertas de prazo, os lembretes de pagamento e as sincronizações.

- **URL configurável:** pela variável de repositório `API_HEALTH_URL` (*Settings → Secrets and variables → Actions → Variables*). Sem ela, usa a URL atual do Render.
- **Teste manual:** **Actions → Keep alive → Run workflow**.
- **Atrasos:** o GitHub pode atrasar execuções agendadas em horário de pico, e a API pode hibernar de vez em quando. Um job diário que cair nesse intervalo não roda naquele dia.
- **Desativação:** o GitHub **desativa workflows agendados após 60 dias sem commits** no repositório. Quando isso acontecer, reative na aba Actions.

## N9. Primeiro acesso e verificação

1. **Criar o administrador**, da sua máquina, apontando para o Neon (PowerShell, dentro deste repositório):

   ```powershell
   $env:POSTGRES_HOST="<host>"; $env:POSTGRES_USER="<usuário>"; $env:POSTGRES_PASSWORD="<senha>"; $env:POSTGRES_DB="<banco>"; $env:PGSSLMODE="require"; $env:JWT_SECRET_KEY="qualquer-coisa"; $env:RESEND_API_KEY="x"
   python scripts/create_admin.py
   ```

2. **API:** `https://<api>.onrender.com/api/v1/health` deve responder `"status": "ok"` e `"database": "connected"`.
3. **Login:** entre no site do Netlify com o administrador.
4. **Imagens:** troque uma logo e confira se a URL dela começa com `MEDIA_PUBLIC_BASE_URL`.
5. **Drive:** na página de Processos, clique em **Conectar Google Drive**. Depois envie, baixe e exclua um documento, e confira a pasta `Sistema Advocacia — Documentos/<número do processo>/` no Drive.

## N10. Ordem dos deploys e cuidados

- **Variáveis antes do merge:** quando uma mudança exige variável nova (como `MEDIA_BUCKET` ou `DOCUMENT_STORAGE`), configure no Render **antes** do merge. Senão, o deploy falha e o Render mantém a versão anterior no ar.
- **Backend antes do frontend:** quando uma história mexe nos dois, faça o deploy do backend antes. A API recusa campos desconhecidos (`extra="forbid"`), e um frontend mais novo que a API recebe **422 "Extra inputs are not permitted"**.
- **Deploy falhou?** Veja **Render → Events/Logs**. Os erros mais comuns:
  - variável obrigatória faltando (`Field required`, `MEDIA_BUCKET must be set`, `DOCUMENT_STORAGE must be 'drive'`);
  - falha de conexão com o Neon (host com `-pooler` ou `PGSSLMODE` ausente).

---

# Anexo — Deploy em VPS Hostinger (Ubuntu 22.04)

Guia usado na US20, antes da migração para a nuvem: VPS zerada → API em produção → domínio + HTTPS → CI/CD automático.

---

## Índice

1. [Acesso inicial e hardening básico](#1-acesso-inicial-e-hardening-básico)
2. [Criar usuário deploy](#2-criar-usuário-deploy)
3. [Instalar dependências](#3-instalar-dependências)
4. [Clonar e configurar o projeto](#4-clonar-e-configurar-o-projeto)
5. [Nginx — HTTP (sem domínio)](#5-nginx--http-sem-domínio)
6. [Subir a aplicação](#6-subir-a-aplicação)
7. [Domínio + HTTPS com Certbot](#7-domínio--https-com-certbot)
8. [CI/CD — GitHub Actions com usuário deploy](#8-cicd--github-actions-com-usuário-deploy)

---

## 1. Acesso inicial e hardening básico

A Hostinger entrega a VPS com acesso root via senha. Faça isso primeiro.

```bash
# Na sua máquina local — conecta como root
ssh root@<IP_DA_VPS>
```

### 1.1 Atualizar o sistema

```bash
apt update && apt upgrade -y
```

### 1.2 Trocar porta SSH (opcional mas recomendado)

Edite `/etc/ssh/sshd_config`:

```bash
nano /etc/ssh/sshd_config
```

Altere ou adicione:
```
Port 2222          # qualquer porta acima de 1024
PermitRootLogin no # depois de criar o usuário deploy
PasswordAuthentication no # depois de adicionar sua chave SSH
```

> **Atenção:** só desative `PasswordAuthentication` e `PermitRootLogin` **depois** de ter configurado as chaves SSH no usuário deploy e testado o acesso.

Reinicie o SSH:
```bash
systemctl restart ssh
```

### 1.3 Firewall (UFW)

```bash
ufw allow 2222/tcp   # porta SSH que você escolheu (ou 22 se não mudou)
ufw allow 80/tcp     # HTTP
ufw allow 443/tcp    # HTTPS (para quando tiver domínio)
ufw enable
ufw status
```

---

## 2. Criar usuário deploy

```bash
# Ainda como root na VPS
adduser deploy
usermod -aG sudo deploy
```

### 2.1 Adicionar chave SSH ao usuário deploy

Na **sua máquina local**, copie a chave pública:
```bash
# Gera a chave se ainda não tiver
ssh-keygen -t ed25519 -C "deploy@vps"

# Mostra a chave pública — copie o output
cat ~/.ssh/id_ed25519.pub
```

De volta na VPS (como root):
```bash
mkdir -p /home/deploy/.ssh
echo "COLE_SUA_CHAVE_PUBLICA_AQUI" >> /home/deploy/.ssh/authorized_keys
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
```

### 2.2 Testar acesso antes de bloquear senha

```bash
# Na sua máquina local — novo terminal
ssh -p 2222 deploy@<IP_DA_VPS>
```

Se entrou, pode agora editar `/etc/ssh/sshd_config` e setar:
```
PermitRootLogin no
PasswordAuthentication no
```
```bash
systemctl restart ssh
```

---

## 3. Instalar dependências

Execute como usuário **deploy** (com sudo):

### 3.1 Docker

```bash
sudo apt install -y ca-certificates curl gnupg lsb-release

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Adicionar deploy ao grupo docker (sem precisar de sudo no docker):
```bash
sudo usermod -aG docker deploy
# Reconecte o SSH para o grupo ter efeito
exit
ssh -p 2222 deploy@<IP_DA_VPS>
```

Verificar:
```bash
docker --version
docker compose version
```

### 3.2 Nginx

```bash
sudo apt install -y nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## 4. Clonar e configurar o projeto

```bash
# Cria o diretório padrão do pipeline de CD
sudo mkdir -p /home/deploy/apps
sudo chown deploy:deploy /home/deploy/apps

cd /home/deploy/apps
git clone https://github.com/<SEU_ORG>/tppe-advocacia-backend.git
cd tppe-advocacia-backend
```

### 4.1 Criar o arquivo `.env`

```bash
cp .env.example .env
nano .env
```

Preencha **todos** os valores de produção:

```env
APP_ENV=production
API_V1_PREFIX=/api/v1
FRONTEND_URL=http://<IP_DA_VPS>       # troca por https://seu-dominio.com quando tiver
FRONTEND_URL_ALT=http://<IP_DA_VPS>

API_HOST_PORT=8000

POSTGRES_USER=advocacia_user
POSTGRES_PASSWORD=<SENHA_FORTE>
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=advocacia_db

# python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=<GERE_AQUI>
JWT_EXPIRE_MINUTES=60
PASSWORD_RESET_EXPIRE_MINUTES=30

RESEND_API_KEY=re_xxxxxxxxxxxx
RESEND_FROM_EMAIL=noreply@seu-dominio.com

# demais variáveis...
```

> Proteja o arquivo:
> ```bash
> chmod 600 .env
> ```

---

## 5. Nginx — HTTP (sem domínio)

Enquanto não tiver domínio, o Nginx vai fazer proxy pelo IP da VPS.

### 5.1 Criar configuração

```bash
sudo nano /etc/nginx/sites-available/advocacia-api
```

Cole:

```nginx
server {
    listen 80;
    server_name _;    # aceita qualquer host — troca pelo domínio depois

    # tamanho máximo de upload (ajuste conforme MAX_FILE_SIZE_MB no .env)
    client_max_body_size 10M;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

### 5.2 Ativar e testar

```bash
sudo ln -s /etc/nginx/sites-available/advocacia-api /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default   # remove página padrão do nginx
sudo nginx -t                                  # verifica sintaxe
sudo systemctl reload nginx
```

Acesse `http://<IP_DA_VPS>/api/v1/health` — deve retornar `{"status":"ok"}`.

---

## 6. Subir a aplicação

```bash
cd /home/deploy/apps/tppe-advocacia-backend
docker compose up -d --build
docker compose logs -f   # acompanha os logs — Ctrl+C para sair
```

Verificar status dos containers:
```bash
docker compose ps
```

Todos devem estar `healthy` ou `running`.

---

## 7. Domínio + HTTPS com Certbot

> Faça isso somente após apontar o DNS do domínio para o IP da VPS e aguardar a propagação (pode levar até 24h, geralmente menos).

### 7.1 Apontar DNS

No painel do seu registrador de domínio, crie um registro **A**:

| Tipo | Nome | Valor         |
|------|------|---------------|
| A    | @    | `<IP_DA_VPS>` |
| A    | www  | `<IP_DA_VPS>` |

Verifique propagação:
```bash
nslookup api.vitorfrancaadv.com.br
```

### 7.2 Instalar Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
```

### 7.3 Atualizar configuração do Nginx com o domínio

```bash
sudo nano /etc/nginx/sites-available/advocacia-api
```

Troque `server_name _;` por:
```nginx
server_name api.vitorfrancaadv.com.br www.api.vitorfrancaadv.com.br;
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

### 7.4 Emitir certificado SSL

```bash
sudo certbot --nginx -d api.vitorfrancaadv.com.br -d www.api.vitorfrancaadv.com.br
```

O Certbot edita o Nginx automaticamente e configura redirect HTTP→HTTPS.

### 7.5 Renovação automática

O Certbot já instala um timer systemd. Verifique:
```bash
sudo systemctl status certbot.timer
```

Teste a renovação:
```bash
sudo certbot renew --dry-run
```

### 7.6 Atualizar `.env` com o domínio

```bash
nano /home/deploy/apps/tppe-advocacia-backend/.env
```

```env
FRONTEND_URL=https://vitorfrancaadv.com.br
FRONTEND_URL_ALT=https://www.vitorfrancaadv.com.br
GOOGLE_REDIRECT_URI=https://api.vitorfrancaadv.com.br/api/v1/integrations/google/callback
```

```bash
docker compose up -d   # recria containers com novo .env
```

---

## 8. CI/CD — GitHub Actions com usuário deploy

O pipeline `.github/workflows/cd.yaml` faz SSH na VPS, executa `git pull` e `docker compose up`. Precisa de uma chave SSH dedicada para o GitHub.

### 8.1 Gerar par de chaves SSH dedicado para o CI

Na **VPS**, como usuário deploy:

```bash
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/github_actions -N ""
```

Isso cria:
- `~/.ssh/github_actions` — chave **privada** (vai para o GitHub)
- `~/.ssh/github_actions.pub` — chave **pública** (fica na VPS)

### 8.2 Autorizar a chave na VPS

```bash
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

### 8.3 Configurar Secrets no GitHub

No repositório GitHub → **Settings → Secrets and variables → Actions → New repository secret**:

| Secret         | Valor                                           |
|----------------|-------------------------------------------------|
| `VPS_HOST`     | IP da VPS (`123.456.789.0`)                     |
| `VPS_USER`     | `deploy`                                        |
| `VPS_SSH_KEY`  | Conteúdo **completo** de `~/.ssh/github_actions` (chave privada) |
| `VPS_SSH_PORT` | `2222` (ou `22` se não mudou)                   |

Para ler a chave privada:
```bash
cat ~/.ssh/github_actions
# Copie todo o output, incluindo as linhas BEGIN e END
```

### 8.4 Permissão do usuário deploy para docker sem senha

O pipeline roda `docker compose up -d --build`. O usuário deploy já está no grupo `docker`, então não precisa de sudo.

Verifique:
```bash
docker compose ps   # deve funcionar sem sudo
```

### 8.5 Garantir que o diretório do projeto existe na VPS antes do primeiro push

O pipeline faz `cd /home/deploy/apps/tppe-advocacia-backend/` — o repositório já precisa estar clonado lá (seção 4). O CD **não clona**, só faz `git pull`.

### 8.6 Fluxo do pipeline

```
push para main
    ↓
SSH na VPS como deploy
    ↓
git pull origin main
    ↓
docker compose up -d --build --remove-orphans
    ↓
docker image prune -f
    ↓
Health check: GET /api/v1/health (5 tentativas, 20s de espera)
    ↓ (se falhar)
Rollback: git checkout HEAD~1 + docker compose up
```

### 8.7 Testar o pipeline manualmente

```bash
# Na VPS como deploy — simula o que o CI faz
cd /home/deploy/apps/tppe-advocacia-backend
git pull origin main
docker compose up -d --build --remove-orphans
docker image prune -f
curl http://localhost:8000/api/v1/health
```

Se funcionar aqui, vai funcionar no CI.

---

## Comandos úteis no dia a dia

```bash
# Ver logs da API
docker compose logs -f api

# Ver logs do scheduler
docker compose logs -f scheduler

# Reiniciar só a API (sem rebuild)
docker compose restart api

# Rebuild completo
docker compose up -d --build

# Ver uso de disco/memória
docker stats

# Entrar no container da API
docker compose exec api bash

# Entrar no banco
docker compose exec db psql -U advocacia_user -d advocacia_db
```

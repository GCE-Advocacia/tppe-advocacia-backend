# Deploy — VPS Hostinger (Ubuntu 22.04)

Guia completo: VPS zerada → API em produção → domínio + HTTPS → CI/CD automático.

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

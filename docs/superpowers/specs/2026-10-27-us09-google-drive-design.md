# US09 — Documentos dos processos no Google Drive (desenho)

Data: 2026-10-27 · Repositórios: `tppe-advocacia-backend` e `tppe-advocacia-frontend`
· História: [US09](https://gce-advocacia.github.io/tppe-advocacia-docs/gce/backlog/us09/)

## Por que

Os documentos anexados aos processos hoje ficam no disco do servidor (`LocalDocumentStorage`).
No Render, esse disco é apagado a cada deploy ou reinício, então qualquer documento enviado se
perde. Além disso, o escritório pediu para acessar os documentos também pelo próprio Google
Drive, organizados por processo.

## Objetivos

- Guardar os documentos dos processos no Google Drive do escritório, com uma pasta por processo
  nomeada pelo **número do processo**, que é como o escritório procura.
- Manter a página do processo funcionando como hoje: enviar, listar, baixar e excluir, com as
  mesmas permissões.
- Deixar o administrador conectar e desconectar a conta Google do escritório por um botão na
  página de Processos.
- Avisar com clareza quando o Drive não estiver conectado ou falhar, e registrar a falha.

## Fora do escopo

- Anexar ao sistema arquivos que já estão no Drive (Google Picker).
- Refletir no sistema mudanças feitas direto no Drive. O escritório só **abre e baixa** pelo
  Drive; quem cria, renomeia e apaga é o sistema.
- Migrar documentos já salvos em disco. Em produção, o banco do Neon começou vazio.
- Renomear a pasta quando o número do processo for editado *(decisão minha: o caso é raro; a
  pasta guarda o número da época em que foi criada)*.

## O que não pode acontecer

- Documento com link público ou compartilhado fora da conta do escritório.
- Documento salvo no disco do Render em produção. Se o Drive não estiver disponível, o upload
  falha; ele **não** cai silenciosamente no disco local.
- O sistema enxergar ou alterar arquivos do Drive que ele não criou (por isso o escopo
  `drive.file`).
- Um usuário comum conseguir conectar, trocar ou desconectar a conta do Drive.

## Decisões tomadas com o Artur

1. **Organização:** uma pasta raiz do sistema e uma subpasta por processo, com o número do
   processo no nome.
2. **Uso pelo escritório:** só abrir e baixar no Drive.
3. **Conexão:** feita pelo administrador, com um botão na **página de Processos** (não há página
   de Configurações). Usuários comuns não veem o botão.
4. **Sem conexão:** anexar um documento mostra um erro pedindo para conectar o Drive.
5. **Uma conexão para o escritório inteiro**, e não uma por usuário.
6. **Excluir no sistema** manda o arquivo para a lixeira do Drive.
7. **Falhas** ficam nos logs de integração e geram o aviso aos administradores que o Datajud já usa.
8. **Desenvolvimento** continua podendo usar o disco local por configuração; produção usa só o Drive.

## Comportamento

### Conexão (administrador)

- A página de Processos mostra para administradores um bloco "Google Drive":
  - desconectado: botão **Conectar Google Drive**;
  - conectado: e-mail da conta conectada e botão **Desconectar**.
- Conectar abre o consentimento do Google (OAuth, Authorization Code, `access_type=offline`,
  `prompt=consent`) com o escopo `https://www.googleapis.com/auth/drive.file`. Ao voltar, o
  frontend mostra uma mensagem de sucesso ou de erro.
- **Uma única conexão para o escritório inteiro**: não é por usuário, como no
  Google Calendar. Todos os uploads usam essa conta. Conectar de novo substitui a conexão
  anterior.
- Desconectar apaga o refresh token do banco e tenta revogá-lo no Google (falha na revogação não
  impede a desconexão). Os documentos continuam no Drive. Enquanto estiver desconectado, enviar,
  baixar e excluir documentos do Drive falham com a mensagem de "Drive não conectado".

### Documentos

- **Enviar:** mesmas validações de hoje (tamanho e tipo detectado pelo conteúdo, nome original
  higienizado). O arquivo vai para a pasta do processo, criada na primeira vez que for
  necessária. No Drive, o arquivo leva o nome original enviado pelo usuário.
- **Listar:** sem mudança; vem do banco.
- **Baixar:** o backend busca o arquivo no Drive e devolve ao usuário com o mesmo
  `Content-Type` e nome de hoje. O usuário nunca recebe um link do Drive.
- **Excluir:** mesma permissão de hoje (administrador ou quem enviou). O arquivo vai para a
  **lixeira** do Drive (o Google guarda por 30 dias), e não é apagado definitivamente.

### Estrutura no Drive

```
Meu Drive/
└── Sistema Advocacia — Documentos/        ← pasta raiz, criada na primeira necessidade
    ├── 0001234-56.2024.8.26.0100/          ← uma pasta por processo
    │   ├── Petição inicial.pdf
    │   └── Procuração.pdf
    └── 0009876-54.2023.8.26.0001/
```

- *Decisão minha:* o nome da pasta raiz é fixo: `Sistema Advocacia — Documentos`.
- *Decisão minha:* o nome da pasta do processo é o número no formato CNJ
  (`NNNNNNN-DD.AAAA.J.TR.OOOO`) quando o número salvo tiver 20 dígitos. Se não tiver, usa o
  número como está salvo.
- O sistema guarda no banco os IDs da pasta raiz e das pastas de cada processo, e **não procura
  pastas por nome**. Com `drive.file`, ele só enxerga o que criou. Se uma pasta guardada tiver
  sido apagada no Drive (o Google responde 404 ou ela está na lixeira), o sistema cria outra e
  atualiza o ID.

### Falhas

- **Drive não conectado:** a API responde **409** com o código `GOOGLE_DRIVE_NOT_CONNECTED`. O
  frontend mostra:
  - para administradores: "Conecte o Google Drive para anexar documentos." (com o botão por perto);
  - para os demais: "O Google Drive não está conectado. Peça a um administrador para conectar."
- **Acesso revogado ou expirado** (o Google responde `invalid_grant`): o sistema apaga a
  credencial, ou seja, passa a considerar o Drive desconectado, e responde como no item anterior.
  Isso também é registrado como falha.
- **Outras falhas do Google** (timeout, 5xx, cota): a API responde **503** com o código
  `GOOGLE_DRIVE_UNAVAILABLE` e uma mensagem genérica ("Não foi possível acessar o Google Drive.
  Tente novamente.").
- **Registro:** toda falha de comunicação com o Drive cria uma linha em `external_api_logs`
  (provider `GOOGLE_DRIVE`; operações `DOCUMENT_UPLOAD`, `DOCUMENT_DOWNLOAD`, `DOCUMENT_DELETE`
  e `OAUTH`) e chama o `ExternalApiFailureNotifier`, que já notifica os administradores, com o
  mesmo throttle do Datajud. Sucessos não são registrados *(decisão minha: evita encher o log a
  cada upload)*.
- **Consistência no upload:** se o arquivo foi para o Drive, mas gravar no banco falhar, o
  arquivo é apagado do Drive (como hoje acontece com o disco).
- **Consistência na exclusão:** o registro sai do banco primeiro. Se mandar para a lixeira do
  Drive falhar depois disso, a falha é registrada, mas a exclusão é considerada feita.

### Configuração

| Variável | Uso |
|---|---|
| `DOCUMENT_STORAGE` | `local` (padrão, desenvolvimento) ou `drive`. Em produção (`APP_ENV=production`) precisa ser `drive`, e a API não sobe com outro valor, como já acontece com `MEDIA_BUCKET`. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_TOKEN_ENCRYPTION_KEY` | Já existem e servem para os dois fluxos. |
| `GOOGLE_DRIVE_REDIRECT_URI` | Nova. Callback do Drive (`https://<api>/api/v1/integrations/google-drive/callback`). Também precisa ser cadastrada na credencial OAuth do Google Cloud. |

- `DOCUMENT_STORAGE=drive` com o Google não configurado: a API sobe, mas o botão de conectar
  responde com erro de configuração, e o upload responde "não conectado".
- Cada documento registra onde está guardado (`local` ou `drive`). Assim, documentos antigos
  continuam baixando do disco em desenvolvimento, mesmo depois de trocar a configuração.

## Como o sistema é montado (para quem vai implementar)

Segue os padrões que o backend já usa. É uma orientação, não uma especificação linha a linha.

- **Credencial do escritório:** uma tabela própria (por exemplo, `google_drive_connection`) com
  uma única linha. Guarda o refresh token criptografado com o `TokenCipher` (Fernet) que já
  existe, o e-mail da conta, o ID da pasta raiz, quem conectou e quando. Ela não usa a
  `google_credential` do Calendar, que é uma linha por usuário.
- **Pasta por processo:** uma tabela com o processo e o ID da pasta no Drive (única por processo).
- **Documento:** uma nova coluna `storage` (`local` | `drive`, padrão `local`). Para `drive`, o
  `stored_name` guarda o ID do arquivo no Drive (cabe nos 64 caracteres atuais).
- **OAuth:** reaproveitar o padrão do `google_calendar` (o `GoogleOAuthFlow` e o `state` como JWT
  assinado), com outro escopo, outro redirect e um `state` que identifique o propósito (`drive`),
  para que o `state` do Calendar não sirva no callback do Drive. O callback redireciona para a
  página de Processos do frontend com `?google_drive=connected` ou `?google_drive=error`.
- **Endpoints** (prefixo `/integrations/google-drive`):

| Método e rota | Quem pode | Descrição |
|---|---|---|
| `GET /status` | qualquer usuário logado | `connected` (bool) e `email`; o frontend usa para escolher a mensagem |
| `GET /auth-url` | admin | URL de consentimento |
| `GET /callback` | Google | troca o `code`, guarda a credencial e redireciona |
| `DELETE ""` | admin | desconecta |

- **Storage:** um `GoogleDriveDocumentStorage` ao lado do `LocalDocumentStorage`. Como o
  `path_for()` atual devolve um caminho em disco, a interface precisa mudar para algo que
  devolva o conteúdo (bytes ou stream), e o download do router passa a responder com esse
  conteúdo. O `save` precisa saber o processo (para escolher a pasta).
- **Cliente do Google:** `google-api-python-client`, que já é dependência. Todas as chamadas ao
  Google passam por uma camada pequena que converte erros em `GoogleDriveNotConnectedError` ou
  `GoogleDriveUnavailableError` e grava o log de falha.
- **Testes:** um fake do Drive em memória para os testes unitários e de integração (o
  `google_calendar` já tem um `fake_service.py` como exemplo). Nada nos testes chama o Google de
  verdade.

## Frontend

- Na página de Processos, para administradores: o bloco de status e conexão do Google Drive,
  seguindo o visual e as mensagens do bloco do Google Calendar na Agenda.
- Ao voltar do Google, ler `?google_drive=connected|error`, mostrar a mensagem e limpar o
  parâmetro da URL.
- Na seção de documentos do processo (`ProcessDocumentsSection.tsx`): tratar `409
  GOOGLE_DRIVE_NOT_CONNECTED` e `503 GOOGLE_DRIVE_UNAVAILABLE` com as mensagens acima, no lugar
  do erro genérico.

## Implantação

1. Ativar a Google Drive API no projeto do Google Cloud do escritório e adicionar o escopo
   `drive.file` na tela de consentimento.
2. Cadastrar o `GOOGLE_DRIVE_REDIRECT_URI` na credencial OAuth.
3. No Render: `DOCUMENT_STORAGE=drive` e `GOOGLE_DRIVE_REDIRECT_URI`, além das `GOOGLE_*` que já
   existem. Configurar **antes** do merge, porque a API não sobe em produção sem
   `DOCUMENT_STORAGE=drive`.
4. Fazer deploy do backend **antes** do frontend.
5. O administrador clica em "Conectar Google Drive" na página de Processos.
6. Teste: enviar, baixar e excluir um documento, e conferir a pasta no Drive.

## Fica a critério de quem implementar

- Nomes exatos de tabelas, classes e mensagens de log.
- Upload simples ou *resumable* para o Drive (os arquivos têm até 20 MB).
- Download em memória ou em streaming.
- Como obter o e-mail da conta conectada (por exemplo, `about.get` do Drive).
- Layout exato do bloco do Google Drive na página de Processos.

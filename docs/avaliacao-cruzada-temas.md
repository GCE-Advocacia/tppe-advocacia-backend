# Avaliação cruzada — API de temas e configuração visual

Escopo: US07, US09/US10 e US14. Branch `avaliacao-cruzada`, baseada em `a7bb404`. A `main` local não foi alterada.

## Comportamento resultante

| Operação | Resultado |
| --- | --- |
| PUT em tema oficial | 403, `PREDEFINED_THEME_UPDATE_NOT_ALLOWED`; nenhuma alteração no tema. |
| DELETE de tema oficial | 403, `PREDEFINED_THEME_DELETE_NOT_ALLOWED`. |
| POST `/office-config/themes/{id}/duplicate` | 201; copia paleta e opções de botões, cria personalizado e usa o sufixo `(Cópia)`. Corpo opcional com nome/descrição. |
| Criar/duplicar com seis personalizados ou nove temas totais | 400, `THEME_LIMIT_EXCEEDED`. |
| Excluir personalizado ativo | `theme_id` nulo, cores aplicadas preservadas. |
| Salvar cores independentes dos botões | Aceita `#RGB`, `#RRGGBB`, `#RRGGBBAA`; rejeita strings inválidas com 422. |
| Mutação sem autenticação / por colaborador | 401 / 403 nas operações de criação, edição, exclusão, duplicação e aplicação. |

A configuração continua usando **PATCH /office-config**, conforme o contrato existente. Não foi criada uma rota PUT alternativa. Os campos já existem; nenhuma migration foi necessária.

## Testes

Cobertura acrescentada em:

- `tests/unit/modules/office_config/test_theme_service.py`: proteção de temas oficiais sem atualização/commit.
- `tests/e2e/modules/office_config/test_theme_e2e.py`: TC-S1-01 a TC-S1-05, cota real via HTTP, estado após exclusão e duplicação válida.
- `tests/e2e/modules/office_config/test_office_config.py`: roundtrip dos três campos e dos dois valores de `system_uses_landing_buttons`, validação e preservação após erro.

Os testes HTTP usam autenticação, FastAPI e PostgreSQL real. Execute somente em banco descartável exclusivo para testes, configurando as variáveis `POSTGRES_*`.

```sh
SCHEDULER_ENABLED=false PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/unit/modules/office_config tests/integration/modules/office_config tests/e2e/modules/office_config -q --disable-warnings
```

### Evidências locais

- Suíte de configuração/temas: **409 testes passaram**, em Python 3.10 e PostgreSQL temporário exclusivo.
- Ruff dos sete arquivos Python alterados: lint e formatação aprovados.
- A verificação ampla inicial teve 1.652 aprovações e três falhas preexistentes, reproduzidas na base original: duas em lembretes de pagamento e uma em captura de logs após migrations. Essas correções ficam fora desta entrega; nenhuma alteração em pagamentos ou na configuração de logging foi mantida.

### Compatibilidade anterior à auditoria

A execução completa em Python 3.10 falha na coleta de quatro arquivos já presentes na base, pois importam `datetime.UTC` (disponível a partir do Python 3.11):

- `tests/integration/modules/audit_logs/test_audit_log_repository.py`;
- `tests/unit/modules/articles/test_article_service.py`;
- `tests/unit/modules/audit_logs/test_audit_log_service.py`;
- `tests/unit/modules/users/test_user_service.py`.

O Dockerfile usa Python 3.10, enquanto o workflow GitHub configura Python 3.13. A conferência complementar usou Python 3.12 em ambiente temporário, sem mudar os arquivos desses módulos ou as versões do projeto. É necessário alinhar essa diferença de runtimes com o grupo.

## Pendências de entrega

- A validação manual TC-S1-13/14 em Homologação e Produção depende das URLs, acesso e janela para mudança global de temas. Não foi executada.
- O roteiro e a matriz completa de cobertura estão em `tppe-advocacia-frontend/docs/avaliacao-cruzada-temas.md`.
- Os dois repositórios precisam de PRs vinculados ou de alinhamento com o grupo sobre “PR único”. Nenhum PR foi aberto nesta execução.
- Não marcar a issue como concluída antes dessas verificações e da entrega.

## Texto proposto para o PR do backend

**Título:** test: avaliação cruzada da API de temas e cores

Protege temas oficiais contra edição/exclusão com 403, acrescenta duplicação sujeita à cota e valida os formatos HEX dos botões independentes. Amplia a cobertura unitária e HTTP de permissões, limites, persistência e exclusão do tema ativo sem perda das cores.

Validação local do escopo: 409 testes de configuração/temas aprovados e Ruff aprovado nos arquivos alterados. A interface e seus 57 testes estão na branch de mesmo nome do frontend. Resultados complementares e pendências de Homologação/Produção estão registrados neste documento.

# AXION CRM

CRM da AXION SOLUTIONS com painel comercial, pipeline, follow-up e recebimento de contatos pela API oficial do WhatsApp Business.

## O que esta versão adiciona

- Backend Python/FastAPI com banco SQLite persistente, login e sessões revogáveis.
- Webhook com verificação GET e assinatura HMAC-SHA256 no corpo original do POST.
- Cadastro automático por telefone, mensagens idempotentes e tratamento separado de status.
- Histórico com data/hora e indicação honesta de conteúdo não textual.
- Interface existente preservada, dados do servidor e atualização a cada 5 segundos.
- CRUD, etapas, follow-ups, configurações e importação de backups antigos por API autenticada.
- Testes locais e proteção contra edições que sobrescreveriam mensagens recém-chegadas.

**Estado da integração:** código implementado; ativação e teste real no WhatsApp dependem de hospedagem e credenciais da Meta. Não há envio automático nesta versão. Não foi conectado nem migrado o número da empresa.

## Começar

Leia [o passo a passo de instalação e ativação](docs/INSTALACAO.md). Ele inclui comandos para Windows/VS Code, importação dos dados antigos, custos estimados de hospedagem e configuração segura do webhook.

**Antes de atualizar o Pages:** exporte o backup da versão antiga e configure o backend. A nova interface exige login e servidor; não usa mais localStorage como banco principal. O workflow publica somente os arquivos da interface.

## Estrutura

| Caminho | Responsabilidade |
| --- | --- |
| `index.html`, `assets/` | Interface, logo original e conexão autenticada ao servidor |
| `backend/` | API, validação de eventos, banco e autenticação |
| `.env.example` | Variáveis necessárias, sem credenciais |
| `tests/` | Testes de API e integração da interface |
| `docs/` | Instalação e limites da validação |
| `scripts/backup_database.py` | Backup consistente do banco persistente |

## Testar

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Veja [o relatório e instruções de teste](docs/TESTES.md). Tokens, senhas, bancos e backups reais não devem entrar no repositório.

**Desenvolvido por AXION SOLUTIONS.**

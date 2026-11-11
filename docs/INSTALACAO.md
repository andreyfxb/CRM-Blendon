# Instalar e ativar o AXION CRM

Esta versão preserva o visual e a logo e adiciona servidor, login e recebimento de mensagens. **O código pronto não significa que o número já está conectado à Meta.** Não houve contratação, migração de número ou envio de mensagens nesta implementação.

## 1. Antes de mudar a versão publicada

1. Na versão antiga, abra Configurações → Exportar backup. Guarde o JSON em local privado.
2. Baixe a branch desta implementação no GitHub, ou abra o pull request para revisar os arquivos.
3. Configure e teste o servidor abaixo **antes de integrar a branch à `main`**. A versão nova exige login; sem servidor configurado ela não oferece cadastro local.
4. Nunca coloque backups reais, senhas, `.env` ou banco SQLite no GitHub.

## 2. Executar no computador (Windows / VS Code)

Abra a pasta do repositório no VS Code. Os comandos abaixo são executados no terminal integrado, na raiz do projeto. Use Python 3.12 ou mais recente.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m backend.security
```

O último comando pede a senha duas vezes, sem exibi-la. Escolha pelo menos 12 caracteres. Ele imprime **um hash**, não a senha. Cole o hash inteiro em `ADMIN_PASSWORD_HASH` no `.env`. Mantenha os `$` do hash. Não compartilhe o hash nem a senha.

No `.env`, ajuste `ADMIN_USERNAME` se desejar. Para o teste local, mantenha as origens `http://localhost:5500` e `http://127.0.0.1:5500`. Os três campos `META_...` podem ficar vazios nesta etapa.

Inicie a API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
```

Em outro terminal, sirva a interface:

```powershell
.\.venv\Scripts\python.exe -m http.server 5500 --bind 127.0.0.1
```

Abra **http://127.0.0.1:5500**. No login, informe:

- Endereço do servidor: `http://127.0.0.1:8000`.
- Usuário: o `ADMIN_USERNAME` definido no `.env`.
- Senha: a que você escolheu ao gerar o hash.

A URL do servidor pode ser salva em `assets/config.js` para facilitar o acesso. **Esse arquivo é público: só pode conter a URL, nunca credenciais.** O token de sessão fica apenas na memória da página; atualizar a página pede login novamente. A sessão expira em 8 horas e Sair a revoga no servidor.

## 3. Importar os cadastros antigos

Depois do login, abra Configurações → Importar JSON e selecione o backup. A importação:

- valida todo o arquivo antes de salvar;
- cria somente contatos com telefone/WhatsApp ainda ausente;
- preserva a etapa e os campos comerciais dos contatos importados;
- identifica conversas antigas como registros importados, sem afirmar que vieram da API;
- nunca substitui contatos existentes nem as configurações do servidor;
- rejeita backups inválidos ou clientes sem telefone/WhatsApp para evitar duplicação na reimportação.

Números brasileiros locais de 10/11 dígitos recebem DDI 55. Para outros países, informe `+DDI`. Não se remove nem se adiciona automaticamente o nono dígito. Se um contato antigo usa uma forma diferente daquela enviada pela Meta, corrija-o antes de importar.

Importar novamente o mesmo JSON não duplica os clientes. Limite: 5 MB / 10.000 clientes por arquivo. Para recuperar o banco completo, veja a seção de backup abaixo.

## 4. Hospedar o backend com HTTPS e banco persistente

Uma opção para esta arquitetura é **um Web Service pago no Render com disco persistente**. O frontend pode continuar no GitHub Pages. Não use o armazenamento temporário de um serviço gratuito como banco de produção.

Referência de custo consultada em 11/11/2026: web service de entrada a partir de aproximadamente **US$ 7/mês**, mais disco a **US$ 0,25/GB/mês**. Um serviço e disco de 1 GB resultariam em cerca de **US$ 7,25/mês**, antes de impostos, câmbio, excedentes e eventuais tarifas do provedor/Meta. **Confira o preço efetivo no painel antes de contratar**: https://render.com/pricing. Não foi criado nenhum serviço pago por esta alteração.

Configuração manual sugerida:

| Campo | Valor |
| --- | --- |
| Runtime | Python 3.12+ |
| Repositório | `andreyfxb/CRM-Blendon` |
| Branch | A branch desta implementação durante a validação |
| Root directory | Vazio (raiz do repositório) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log` |
| Health check | `/health` |
| Disco persistente | Montado em `/var/data` |
| `DATABASE_PATH` | `/var/data/axion.sqlite3` |
| `ALLOWED_ORIGINS` | `https://andreyfxb.github.io` (sem `/CRM-Blendon/`) |

Configure `ADMIN_USERNAME` e `ADMIN_PASSWORD_HASH` como variáveis privadas no painel. Configure os segredos da Meta apenas na próxima etapa. Faça login pela interface usando a URL HTTPS fornecida pelo Render. Não habilite logs de corpo, cabeçalhos ou query string no proxy; o GET de verificação contém o verify token. O comando acima já desativa o access log do Uvicorn.

Use **uma instância e um worker** para esta versão SQLite. O disco precisa ser montado antes da primeira inicialização. Para múltiplas instâncias ou crescimento maior, migre para Postgres e mantenha as garantias de unicidade/transações.

A política de CORS permite apenas origens exatas. No GitHub Pages, a origem é o domínio do usuário inteiro, não uma pasta: scripts de outros projetos sob esse domínio compartilham a mesma origem. Não hospede conteúdo não confiável nesse domínio; para isolamento mais forte, use um domínio dedicado ao CRM. CORS não substitui o login.

## 5. Confirmar o tipo de WhatsApp antes de conectar o número real

**Primeiro confirme com o responsável: o +55 11 97732-1570 usa WhatsApp comum ou WhatsApp Business?** Não exclua a conta do aplicativo e não desconecte o número.

Consulte o fluxo atual de onboarding da Meta e verifique a elegibilidade no painel:

- Documentação oficial de onboarding de usuários do WhatsApp Business App / coexistência: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users
- Embedded Signup: https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/
- Visão geral da Cloud API: https://developers.facebook.com/docs/whatsapp/cloud-api/overview
- Referência oficial de mensagens (atualizada em 04/11/2026): https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/components
- Verificação e assinatura (referência técnica da Meta): https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/ (SDK arquivado; não é usado como dependência).

A coexistência, quando disponível e elegível para a conta/fluxo, é o caminho a avaliar para manter o Business App e a API no mesmo número. **Não assuma que está habilitada para este número ou que WhatsApp comum oferece o mesmo fluxo.** Consulta direta à documentação oficial realizada em 11/11/2026: a página de coexistência está atualizada em 29/10/2026. Ela exige Business App 2.24.17 ou posterior e um fluxo de Parceiro de Soluções/Provedor de Tecnologia com Cadastro Incorporado e registro de sessão. Os requisitos e a elegibilidade precisam ser reconferidos no painel para esta conta antes da ativação. Não é apenas digitar o telefone no CRM. Não foi realizada migração nem conexão real.

Esta entrega recebe **novas mensagens via `messages`**. Não implementa onboarding automatizado, importação do histórico antigo do aplicativo, nem espelhamento de mensagens enviadas pelo celular (`smb_message_echoes`). Esses eventos são ignorados de propósito, para não cadastrar saídas como entradas. A documentação exige o processamento dos campos de sincronização/echo e orienta iniciar a sincronização dos contatos e histórico em até 24 horas após o onboarding. Para esse fluxo, implemente e valide essa etapa ou use um provedor oficial que a execute antes de concluir a conexão. Não prometa sincronização completa de coexistência com esta versão.

## 6. Configurar a Meta e o webhook (comece pelo número de teste)

Com o servidor HTTPS disponível, use um app empresarial com o produto WhatsApp/Cloud API no painel Meta for Developers. Comece com os recursos de teste fornecidos pela Meta. Os nomes dos menus podem mudar.

1. Identifique o **App Secret** do app: salve no ambiente privado do servidor como `META_APP_SECRET`.
2. Gere uma sequência aleatória longa para `META_VERIFY_TOKEN`. É uma senha de verificação escolhida por você, diferente do token de acesso da API.
3. Copie o **Phone Number ID** do número de teste como `META_PHONE_NUMBER_ID`. É um identificador do painel, **não** o telefone `11977321570`.
4. Reinicie o backend para carregar as variáveis. Configure a Callback URL como `https://SEU-SERVIDOR/webhooks/whatsapp` e o Verify token com o mesmo valor do servidor.
5. Conclua Verify and Save. O GET retorna `hub.challenge` em texto quando o token confere.
6. Assine o campo de webhook `messages` e confirme no painel/fluxo oficial que o app está inscrito na conta WhatsApp correta. Somente verificar a callback não garante essa inscrição. Se usar a API de gestão para inscrever, siga a versão atual e use um token com as permissões exigidas, somente em ambiente privado.
7. Envie uma mensagem real de um telefone autorizado para o número de teste. Confira se o contato aparece em Novos contatos, se o nome/telefone conferem e se a mensagem tem data/hora.
8. Envie outra mensagem do mesmo telefone: deve haver um único contato e duas mensagens. Mude a etapa comercial e confirme que outra entrada não a reverte.
9. Só depois de validar o teste e confirmar o tipo de aplicativo/fluxo do número real, configure a conta e o ID real, com autorização do responsável para qualquer mudança que afete o aplicativo.

O servidor não precisa de access token para apenas verificar a assinatura e receber o evento. Esse token pode ser necessário no painel/fluxo de inscrição da Meta, mas nunca deve ser inserido no frontend ou em uma conversa. A primeira fase não faz chamadas de envio e não implementa respostas automáticas.

## 7. Publicar a interface

Após testar o backend e revisar o pull request:

1. Ajuste a URL pública do servidor em `assets/config.js`, se desejar predefini-la.
2. Integre a branch à `main` pelo GitHub.
3. Aguarde o workflow do Pages terminar. Ele agora publica somente `index.html` e `assets/`, não a pasta do backend.
4. Abra https://andreyfxb.github.io/CRM-Blendon/ e faça login.
5. Importe o backup privado antigo. Não apague os dados antigos do navegador até conferir os cadastros importados.

A atualização automática consulta o servidor a cada 5 segundos, sem recarregar a página. Durante edição de campos, modais e Configurações a atualização visual pausa para não apagar o que está sendo digitado. Ao concluir a edição, volta a consultar. Se um evento mudar o cadastro enquanto o formulário estava aberto, o servidor recusa a gravação antiga: feche, atualize e reabra o formulário antes de salvar novamente.

## 8. Backup e recuperação

- Configurações → Exportar backup gera um JSON privado dos contatos e históricos visíveis. Reimportar esse arquivo recupera contatos ausentes e marca as conversas como importadas; não restaura os IDs de eventos nem substitui contatos existentes.
- Para recuperação integral, faça backup consistente do SQLite no servidor: `python scripts/backup_database.py /var/data/axion.sqlite3 /CAMINHO-PRIVADO/axion-backup.sqlite3`. Copie para um armazenamento privado separado do serviço.
- Para restaurar o banco completo, pare a API, preserve uma cópia do banco atual, restaure o arquivo de backup em `DATABASE_PATH` com as permissões corretas e reinicie. Não sobrescreva um banco aberto nem copie apenas o arquivo principal enquanto está em uso (WAL pode conter alterações).
- O backup integral contém clientes, mensagens, IDs processados e sessões. Na recuperação, revogue sessões/troque a senha administrativa antes de reabrir acesso. Trate todo backup como dado privado.

## Limites desta entrega

Uma empresa/número e um administrador por instalação. Sem download de anexos, transcrição de áudio, chatbot, envio de mensagens, notificações push ou importação do histórico da Meta. Tipos não textuais aparecem como `[Áudio]`, `[Imagem]` etc., com legenda quando ela foi fornecida. Eventos de status não criam contatos. Credenciais, hospedagem e um teste real na Meta continuam pendentes até a configuração pelo responsável.

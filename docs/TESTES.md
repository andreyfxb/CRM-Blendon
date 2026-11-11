# Validação desta implementação

## Executado localmente

- **20 testes automatizados da API** passaram em Python 3.12 com FastAPI 0.141.1, Uvicorn 0.41.0 e httpx 0.28.1.
- Teste de integração de DOM (jsdom) conectado ao **servidor FastAPI real local** passou: login, webhook assinado sintético → contato na interface via polling, segunda mensagem sem duplicar contato, preservação da etapa, conflito de edição sem perda de mensagem, edição após atualizar versão, configurações, todas as telas e saída.
- Verificação de sintaxe dos arquivos JavaScript passou.

Os eventos usados nos testes são sintéticos, com assinatura calculada por uma chave exclusiva de teste. **Isso valida o código, não uma conexão real com a Meta.** Nenhuma mensagem foi enviada para o número da empresa.

## Cobertura da API

1. Mensagem cria contato novo sem inventar produto, modelo ou orçamento.
2. Nova entrada preserva o contato existente e sua etapa comercial.
3. Reenvio do mesmo ID é idempotente.
4. Entregas simultâneas do mesmo ID não duplicam contato nem mensagem.
5. Assinatura inválida ou ausente é recusada.
6. Status de leitura/entrega fica separado e não cria contato ou conversa.
7. Outro Phone Number ID e campos de echo são ignorados.
8. Áudio é identificado como áudio, sem transcrição inventada.
9. Ausência de nome usa o telefone como identificação.
10. Normalização de telefone permite associar contato manual à mensagem.
11. Rotas com dados de clientes exigem login.
12. Logout revoga a sessão.
13. GET de verificação retorna challenge em texto e recusa token incorreto.
14. Uma edição antiga não sobrescreve dados após uma mensagem nova.
15. Importação é validada antes de salvar e não duplica contatos.
16. CRUD, configuração e contador de follow-up funcionam.
17. Dados continuam disponíveis após reiniciar a aplicação.
18. Tentativas de login são limitadas e erros não devolvem a senha.
19. CORS permite a origem configurada e respostas não são armazenadas em cache.
20. Requisições acima de 5 MB são recusadas.

## Reproduzir

Na raiz do repositório:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
npm ci --ignore-scripts
npm run check
npm run test:dom
```

O teste DOM requer Node 24+ e Python disponível como `python3`. No Windows, execute `py scripts/run_frontend_tests.py` depois de instalar as dependências na venv ativa, ou ajuste o comando para o executável da venv. Ele inicia uma API e servidor estático nas portas locais 8765 e 5500, cria um banco temporário, usa credenciais **exclusivas de teste** e encerra os servidores. Não aponte a fixture para um banco real.

Há também `tests/frontend.cjs` para Playwright. Para executá-lo em um ambiente com navegador disponível, instale Playwright separadamente, instale o Chromium do Playwright e rode `python scripts/run_frontend_tests.py --browser`. Um Chromium já instalado pode ser informado via `CHROMIUM_PATH`. **O teste com navegador real não foi concluído neste ambiente:** o Chromium não conseguiu abrir o socket de controle (`Operation not permitted`). Por isso, não se afirma validação visual de desktop/celular. O teste DOM é uma validação funcional, não visual.

## Ainda precisa de teste no ambiente final

- Hospedagem HTTPS com disco persistente, reinício/redeploy e recuperação de backup.
- Login e CORS reais a partir do GitHub Pages.
- Verificação do webhook e inscrição do app na conta WhatsApp correta pela Meta.
- Mensagem real do número de teste e, depois, do número da empresa.
- Elegibilidade e fluxo de coexistência conforme o aplicativo usado pelo responsável.
- Revisão visual no navegador e celular antes de integrar a branch à versão publicada.

Não houve contratação, publicação do backend, migração de número, configuração de credenciais reais ou ativação na Meta.

# Kanella Barber Shop

Aplicação de agendamento em **Python / Flask, HTML, CSS e JavaScript puro**, com SQLite. Sem React, Node ou etapa de compilação. Identidade em preto e dourado inspirada na referência fornecida pelo usuário.

## Iniciar no Windows

Abra `iniciar.bat` ou execute nesta pasta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Acesse **http://127.0.0.1:5057**. O servidor usa Waitress, sem modo debug, e escuta somente neste computador por padrão. Pare com Ctrl+C no terminal que o iniciou.

O ambiente `.venv` já foi preparado durante a implementação. O banco é criado automaticamente em `instance/kanella.sqlite3`, sem reservas ou clientes fictícios. O catálogo e o estoque inicial são exemplos editáveis no painel.

## Primeiro acesso administrativo

O e-mail reservado é **ld3w1j@gmail.com**. Nenhuma senha padrão foi criada. Abra `administrador.bat` ou execute:

```powershell
.\.venv\Scripts\python.exe -m flask --app app create-admin
```

Digite uma senha de pelo menos 10 caracteres e confirme. A senha não aparece durante a digitação. Depois entre pela opção **Área administrativa** no rodapé. O mesmo comando redefine a senha de administrador existente. O cadastro público nunca concede acesso administrativo, mesmo que use esse e-mail.

## Fluxos implementados

- **Cliente sem conta:** escolhe dia e horário, serviço(s), nome e WhatsApp; paga na barbearia; recebe um link privado de acompanhamento.
- **Reserva:** pendente ocupa todos os intervalos necessários; aprovação confirma; recusa libera; horários passados não podem ser reservados. O banco impede duas reservas simultâneas para o mesmo intervalo.
- **Administrador:** o Dashboard reúne reservas e pedidos. Em Configurações, é possível editar contato, preços dos serviços, nome, preço, estoque e imagem dos produtos, além das regras de fidelidade. As imagens aceitam JPG, PNG e WebP até 3 MB e ficam armazenadas no banco de dados.
- **Conta opcional:** cadastro com nome, celular, e-mail e senha; login próprio da aplicação; histórico de agendamentos e pedidos.
- **Loja exclusiva da conta:** pomada, óleo para barba, shampoo e pente; carrinho, estoque, retirada e pagamento na barbearia. O pedido reserva o estoque; o cancelamento devolve estoque e pontos.
- **Fidelidade:** inicialmente, 1 ponto a cada R$ 10 de um atendimento concluído e pago, arredondado para baixo por atendimento; 100 pontos dão 10% de desconto em um pedido da loja. O administrador pode alterar esses três valores em Configurações. As regras novas se aplicam a atendimentos concluídos e pedidos realizados depois da alteração; pontos já recebidos e pedidos anteriores são preservados. Os pontos são debitados na reserva do pedido e não podem ser gastos duas vezes.
- **Catálogo:** em Configurações, o administrador cadastra e remove serviços e produtos. Remover retira o item do catálogo, mantendo reservas e pedidos anteriores; em Itens removidos é possível reativá-lo. Produtos novos podem receber imagem depois de cadastrados.
- **Pix opcional:** em Configurações, informe a chave Pix, o nome do recebedor e a cidade e marque a opção para oferecer Pix. A chave telefônica deve incluir +55 e DDD. A aplicação gera QR Code estático e código copia e cola com valor para reservas e pedidos, mantendo pagamento na barbearia. A reserva pendente deve ser aprovada antes do pagamento. A equipe deve verificar o recebimento no aplicativo do banco e registrar o pagamento manualmente; gerar ou copiar o código não confirma o pagamento. Um QR estático já copiado pode continuar pagável mesmo se a reserva ou o pedido for cancelado: a equipe deve tratar devoluções com o cliente. Confira os dados do recebedor e faça uma prova com seu banco antes de receber de clientes. Não há integração bancária nem verificação automática de Pix.

O gerador segue o exemplo de BR Code estático do [Manual de Padrões para Iniciação do Pix do Banco Central](https://www.bcb.gov.br/content/estabilidadefinanceira/pix/Regulamento_Pix/II_ManualdePadroesparaIniciacaodoPix.pdf), consultado em 13/11/2026. Salve o banco SQLite em backup para preservar configurações, cadastros e imagens.

## Agenda e catálogo inicial

Um profissional, todos os dias, das 09h às 19h, com intervalo das 12h às 13h, em blocos de 30 minutos; agendamentos até 30 dias à frente. Fuso `America/Sao_Paulo`. Essa rotina é uma configuração inicial, ainda não confirmada pelo estabelecimento. Regras em `domain.py`.

| Serviço | Valor inicial | Duração |
| --- | --- | --- |
| Corte personalizado | R$ 45 | 30 min |
| Barba & cuidado | R$ 35 | 30 min |
| Sobrancelha | R$ 20 | 30 min |
| Combo corte + barba | R$ 70 | 60 min |
| Experiência Kanella | R$ 85 | 60 min |

Valores e estoque são exemplos: ajuste no painel antes de abrir a agenda aos clientes. Os preços são calculados no servidor e cada reserva preserva os valores da contratação. O Pix é opcional e depende de configuração e verificação manual pela equipe; não há cobrança por cartão nem confirmação automática de pagamento.

## WhatsApp: o que funciona e o que falta configurar

**Disponível:** ao aprovar a reserva, o painel oferece **Enviar confirmação**, que abre `wa.me` com nome, serviços, data, horário e valor. O administrador precisa enviar a mensagem no WhatsApp. Abrir o link não é considerado envio.

**Preparado, mas não ativado:** envio automático pela API oficial do WhatsApp Business. Requer conta e número da Meta, token e template aprovado. Configure no ambiente do processo:

- `WHATSAPP_ACCESS_TOKEN`: token da Meta (segredo).
- `WHATSAPP_PHONE_NUMBER_ID`: identificador do número de envio.
- `WHATSAPP_TEMPLATE_NAME`: template aprovado em `pt_BR` com uma variável de texto no corpo para os detalhes da reserva.
- `WHATSAPP_API_VERSION`: versão suportada da Graph API; padrão `v23.0`, ajustável conforme a conta.

O código só chama a API quando as três configurações obrigatórias existem. Se a API falhar, a aprovação permanece e o painel oferece o envio manual. `accepted` significa aceitação pelo provedor, **não entrega ou leitura**; não há webhook de confirmação de entrega nesta versão. Nenhuma mensagem real foi enviada durante os testes. Valide o template e a integração com a sua conta antes de depender do envio automático.

Para avisar o barbeiro quando um cliente cancelar um agendamento confirmado, configure também `WHATSAPP_CANCELLATION_TEMPLATE_NAME` com um template Meta aprovado em `pt_BR` que tenha uma variável de texto no corpo e cujo conteúdo seja adequado ao aviso de cancelamento. Defina o número de destino em **Administração → WhatsApp**; ele precisa estar apto a receber mensagens da conta comercial. É necessário configurar `WHATSAPP_ACCESS_TOKEN` e `WHATSAPP_PHONE_NUMBER_ID` acima. Cancelamentos pendentes não enviam aviso. O cancelamento é salvo antes da tentativa de envio; falhas não revertem o cancelamento. O painel distingue aviso não configurado, em processamento, aceito pelo provedor e falha. A aceitação não confirma entrega e não há reenvio automático. Em caso de Pix pago fora do sistema, o cliente deve contatar a barbearia sobre o pagamento.

Contato para o cliente falar com a barbearia: salve o número em **Administração → WhatsApp**. Esse contato público não configura a API de envio.

## Estrutura

```text
app.py               servidor, autenticação, API e operações transacionais
domain.py            catálogo inicial, validações e regras de horário
schema.sql           estrutura do SQLite
run.py               inicialização pelo Waitress
templates/index.html página base
static/style.css     identidade visual e layout responsivo
static/app.js        navegação e coordenação das telas
static/booking.js    agendamento
static/club.js       conta, fidelidade e loja
static/admin.js      painel administrativo
static/common.js     chamadas à API, formatação e escape de HTML
tests/               testes de API, concorrência e navegador
instance/            banco e chave da sessão, privados e ignorados pelo Git
```

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes de navegador usam Chrome ou Edge instalado no Windows. Em outro ambiente, execute `python -m playwright install chromium`. Eles usam banco temporário e credenciais exclusivamente de teste, sem alterar os dados do app em execução. As capturas ficam em `test-results/`.

## Dados e implantação

Senhas usam o hash seguro do Werkzeug; sessão com cookie HttpOnly/SameSite, CSRF em gravações, limitação de tentativas de login e reservas, validação no servidor e queries parametrizadas. As operações de reserva e fidelidade usam transações `BEGIN IMMEDIATE`, além da chave única de data/horário. O link privado de reserva concede acesso aos dados desse pedido: não o compartilhe publicamente.

Faça backup do SQLite com a API de backup do SQLite, ou com o servidor parado. Preserve `instance/.secret-key`; é a chave das sessões, não deve ir para Git nem para compartilhamento público. Se usar sincronização de pastas, evite executar o mesmo banco simultaneamente em computadores diferentes.

Os arquivos para implantação no Railway e os passos de configuração estão em [RAILWAY.md](RAILWAY.md). O Dockerfile ativa o modo de produção; fora dele, `HOST` e `PORT` controlam o Waitress, com padrão local `127.0.0.1:5057`.

Limites desta versão: um profissional e expediente fixo; sem redefinição automática de senha por e-mail; reservas pendentes não expiram automaticamente; SQLite adequado à instância única. Não há automação de cobrança nem confirmação real de entrega do WhatsApp.

## Fontes e decisões

Pedido e ajustes do usuário em 09/11/2026: Kanella (imagem de referência), pagamento presencial, confirmação WhatsApp, administrador indicado e preferência por Flask. A solução React inicialmente esboçada em `../barbearia/` foi substituída por este projeto; aquela pasta não participa da execução.

Documentação consultada em 09/11/2026: [Flask — SQLite](https://flask.palletsprojects.com/en/stable/patterns/sqlite3/), [Flask — segurança](https://flask.palletsprojects.com/en/stable/web-security/), [Meta — envio de template](https://www.postman.com/meta/whatsapp-business-platform/request/o65u5m5/send-message-template-text).

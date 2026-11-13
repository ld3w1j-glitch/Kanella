# Preparação da Kanella para Railway

Esta pasta está preparada para implantação, mas **não foi publicada nem conectada a uma conta Railway**. O projeto usa Flask, Waitress e SQLite. O `Dockerfile` inicia o servidor com `APP_ENV=production`, escuta em `0.0.0.0` e usa a porta `PORT` fornecida pelo Railway.

## Antes de publicar

1. Crie um projeto e um serviço vazio no Railway. Use uma única instância: o SQLite deste projeto não deve ser compartilhado entre réplicas.
2. Conecte um volume persistente ao serviço, com ponto de montagem `/data`. O Railway fornece `RAILWAY_VOLUME_NAME` e `RAILWAY_VOLUME_MOUNT_PATH` automaticamente; não preencha essas variáveis manualmente. O banco e as imagens enviadas pelos produtos serão gravados em `/data/kanella.sqlite3`.
3. Nas variáveis do serviço, adicione `SECRET_KEY` com uma chave aleatória própria de pelo menos 32 caracteres. Exemplo para gerar no seu computador: `python -c "import secrets; print(secrets.token_hex(32))"`. Copie o resultado diretamente para as variáveis do Railway. Guarde-o em local seguro, não em arquivos do projeto ou no Git. Mantenha o mesmo valor nas próximas versões.
4. Opcionalmente, defina `ADMIN_EMAIL` com o e-mail do gestor. Se omitido, será usado o e-mail já previsto no aplicativo. Não existe senha administrativa padrão. Não configure as variáveis de WhatsApp automático sem uma conta e um template válidos.
5. Nas configurações do serviço, defina o caminho de healthcheck como `/health`. O healthcheck verifica a inicialização, não substitui monitoramento contínuo. Um serviço com volume pode ter breve interrupção durante atualizações.

Sem volume ou sem `SECRET_KEY` adequada, a aplicação em produção encerra a inicialização, para evitar operar acidentalmente com dados temporários ou sessão insegura. Essas validações não alteram o uso local normal.

## Enviar o código

Opção por GitHub: conecte o repositório no Railway e, se o repositório contiver outras pastas, defina a raiz do serviço como `kanella-flask`. O Railway detecta o `Dockerfile`. Não adicione `instance/`, `.env`, backups ou segredos ao repositório.

Opção por diretório local: instale e autentique a [Railway CLI](https://docs.railway.com/cli), vincule o projeto e o serviço previamente criados com `railway link` e, dentro desta pasta, execute `railway up . --path-as-root`. Esse comando envia e inicia uma implantação; não use `--no-gitignore`. Confira projeto e serviço vinculados antes de executá-lo. `.railwayignore` e `.dockerignore` excluem o banco local, backups, ambientes virtuais e arquivos de trabalho.

## Criar o login do gerenciador

Depois de iniciar o serviço, abra `railway ssh` no serviço correto e execute no shell remoto:

```sh
python -m flask --app app create-admin
```

Informe a senha duas vezes nos prompts, sem digitá-la na linha de comando ou registrá-la em arquivos. O e-mail é o de `ADMIN_EMAIL` ou o padrão já previsto. Esse comando também redefine a senha do administrador existente. No site, acesse **Gerenciador** no menu; uma conta comum não recebe privilégios administrativos.

Depois, gere um domínio público nas configurações do Railway e valide o acesso HTTPS, o login, a criação de reserva e o fluxo da loja usando dados de teste. Em produção, o Waitress informa à aplicação o esquema HTTPS, pois o Railway termina a conexão TLS no proxy e o Waitress descarta cabeçalhos de proxy não confiáveis. Confira se o IP do cliente chega corretamente ao serviço antes de depender da limitação de tentativas; não exponha diretamente a porta do processo por outro caminho sem rever essa configuração.

## Dados atuais e recuperação

O volume começa vazio: a primeira inicialização cria um banco novo com catálogo de exemplo. **O banco local não é enviado nem migrado automaticamente.** Se for necessário levar os dados atuais, prepare uma cópia íntegra com a API de backup do SQLite e planeje a importação com o serviço e o banco de destino parados; não substitua um SQLite aberto nem envie o arquivo `instance/.secret-key` ou backups para o Git. Faça backup do volume e teste a restauração antes de receber dados reais. As imagens de produtos estão dentro do SQLite.

No painel, ajuste preços, serviços, estoque e WhatsApp. Para usar Pix, configure e ative a chave, o recebedor e a cidade e confira no banco antes de receber de clientes. O QR estático não confirma pagamentos automaticamente. A entrega de WhatsApp automático também depende de configuração externa e não está ativa por esta preparação.

Para aviso automático ao barbeiro quando uma reserva confirmada for cancelada, configure `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` e `WHATSAPP_CANCELLATION_TEMPLATE_NAME`, além do número de destino em **Administração → WhatsApp**. O template de cancelamento precisa ser aprovado pela Meta em `pt_BR` com uma variável de texto no corpo, adequada ao aviso; não reutilize o template de confirmação do cliente. O cancelamento é persistido antes do envio, e a aceitação pelo provedor não confirma entrega. Falhas são registradas e não há reenvio automático. Cancelamentos ainda pendentes não geram aviso. A integração deve ser configurada e validada na conta Meta; não fica ativa apenas com o deploy. Como Pix estático não confirma pagamento, o cliente que tiver pago deve contatar a barbearia sobre o pagamento.

## Referências

Documentação oficial consultada em 13/11/2026: [Dockerfiles](https://docs.railway.com/builds/dockerfiles), [volumes](https://docs.railway.com/volumes), [healthchecks](https://docs.railway.com/deployments/healthchecks), [variáveis](https://docs.railway.com/variables), [SSH](https://docs.railway.com/cli/ssh) e [redirecionamento e cabeçalhos](https://docs.railway.com/networking/public-networking/specs-and-limits).

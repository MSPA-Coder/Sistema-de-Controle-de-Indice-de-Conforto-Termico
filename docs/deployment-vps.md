# Implantação no VPS

Esta implantação publica o ICT pelo Nginx em
`https://conforto-mspa.duckdns.org`. O Docker publica o ICT apenas em
`127.0.0.1:5401` e o PostgreSQL apenas em `127.0.0.1:5402`; o coletor não expõe
porta alguma. Não abra essas portas no firewall nem na OCI.

O código no VPS é um espelho do `main`: toda mudança nasce na máquina de
desenvolvimento, vai ao GitHub e só então chega ao servidor. O servidor não é
lugar de editar código — `~/deploy.sh` recusa implantar se encontrar alteração
não commitada.

O VPS mantém a sua própria base, independente da instalação local: os dois
ambientes nunca sincronizam dados automaticamente.

## Primeira instalação

O repositório é privado. O VPS o lê por uma *deploy key* somente-leitura,
registrada no GitHub em **Settings → Deploy keys** e apontada pelo apelido
`github-conforto` em `~/.ssh/config`:

```
Host github-conforto
    HostName github.com
    User git
    IdentityFile ~/.ssh/deploy_conforto
    IdentitiesOnly yes
```

Com Docker Engine e o plugin Compose já instalados, clone o repositório e crie
os arquivos locais não versionados:

```bash
mkdir -p ~/apps
git clone git@github-conforto:MSPA-Coder/Sistema-de-Controle-de-Indice-de-Conforto-Termico.git \
  ~/apps/conforto-termico
cd ~/apps/conforto-termico
cp .env.docker.example .env.docker
mkdir -p .secrets .certs
touch .certs/local-root-ca.crt
python scripts/configurar_segredos.py
```

`.certs/local-root-ca.crt` pode ficar vazio no VPS — o arquivo precisa existir
porque o Compose o monta como secret, mas a CA local só é usada no ambiente de
desenvolvimento Windows. A senha do PostgreSQL precisa continuar legível pelos
serviços que a consomem, inclusive o próprio PostgreSQL; o token interno é
legível somente pelo usuário da aplicação.

Emita o certificado e publique a configuração do Nginx:

```bash
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d conforto-mspa.duckdns.org
sudo nginx -t
sudo systemctl reload nginx
```

Suba a pilha:

```bash
docker compose --env-file .env.docker -f compose.yaml up -d --build --wait
docker compose --env-file .env.docker -f compose.yaml ps
```

O serviço `schema` aplica as migrações Alembic e encerra com código 0; ICT e
coletor só ficam saudáveis depois disso.

## Atualização

A implantação é feita por `~/deploy.sh`, que confere a árvore, traz o `main`,
reconstrói a imagem, espera os health checks e valida o endereço público:

```bash
~/deploy.sh conforto --check   # mostra o que mudaria, sem alterar nada
~/deploy.sh conforto           # implanta
~/deploy.sh --status           # estado dos quatro projetos do VPS
```

O script aborta quando encontra alteração não commitada no servidor. Nesse caso
a correção é levar a mudança para a máquina de desenvolvimento, commitar e
enviar ao GitHub — nunca commitar no VPS.

Antes de mudanças de schema, gere um backup pela área Sistema autenticada ou
por `pg_dump` no serviço PostgreSQL.

## Rollback

Preserve o backup, selecione uma revisão já validada e suba de novo:

```bash
git log --oneline -5
git checkout <commit-validado>
docker compose --env-file .env.docker -f compose.yaml up -d --build --wait
```

Esse estado é destacado (`detached HEAD`); a implantação seguinte pelo
`deploy.sh` volta a alinhar o servidor com o `main`.

## O que não é versionado

`.secrets/` (`postgres_password.txt`, `internal_token.txt`) e `.certs/` existem
apenas no servidor; um reclone precisa restaurá-los, ou o build falha e o banco
fica inacessível. Os dados ficam nos volumes `conforto-termico_postgres_data` e
`conforto-termico_app_instance`, fora da pasta do código: substituir o diretório
do projeto não os afeta.

Não use `docker compose down --volumes`: o volume contém o banco de dados.

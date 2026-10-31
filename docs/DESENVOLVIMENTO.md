# Desenvolvimento e validação

## Gate de tipos incremental

O estágio `quality` executa Ruff, `mypy` estrito e pytest. O conjunto pequeno
de fronteiras está em `tool.mypy.files` no `pyproject.toml`; imports mantêm
seus tipos (`follow_imports=silent`), sem esconder erros dos arquivos
selecionados. Amplie por fronteira, com contratos concretos, sem `Any` ou
ignores generalizados. As anotações não substituem validação de payloads,
restrições do PostgreSQL ou os testes de navegador.

## Piloto de navegador isolado

Construa com `docker compose -p conforto-browser-tests -f compose.browser.yaml build`.
Com os mesmos `-p` e `-f`, suba `up -d --no-build --wait browser-coletor`, execute
`run --rm browser-tests` e finalize com `down`. Somente PostgreSQL tmpfs do
piloto é descartado; não há volumes operacionais. `BROWSER_APP_IMAGE` e
`BROWSER_POSTGRES_IMAGE` aceitam candidatos já construídos, sem rebuild.
Fixtures montadas externamente não entram no runtime. Sem portas no host,
contas reais ou dependências externas reais. Falhas deixam PNG em
`.browser-results` (ignorado pelo Git).

O piloto Chromium cobre decimal BR/EUA no ciclo manual, dado antigo, 400 de
domínio versus 502 de transporte, ACL server-side e série pequena de 48
medições. Um provedor meteorológico HTTP controlado mantém 24 linhas em
staging por uma barreira: CSV/cópia não as publicam. Depois de concluir,
exportação/cópia funcionam e replay não duplica histórico. Não valida hardware
ou ciência. ICT e API do coletor usam a mesma imagem candidata.


## Ambiente reproduzível

Use Docker Compose para aplicação, PostgreSQL, migrações e ferramentas. No host,
o único Python do projeto é o venv opcional do laço rápido (ver `AGENTS.md`);
nada vai para o Python global.

Prepare a instalação local:

```powershell
Copy-Item .env.docker.example .env.docker
docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.15-slim `
  python scripts/configurar_segredos.py
docker compose --env-file .env.docker config --quiet
```

Os segredos ficam em `.secrets/` e não devem ser impressos ou versionados. Em
uma instalação existente, não execute o gerador com `--force` sem planejar a
rotação: a chave de sessão muda e invalida sessões.

O script gera as duas senhas do PostgreSQL, raízes físicas independentes para
os tokens internos de leitura e controle e a chave de sessão.

São dois papéis no banco. `postgres_password` é do papel administrativo
(`POSTGRES_USER`, superusuário, dono das tabelas), que só o `postgres`, o
`db-provision` e o `schema` (Alembic) recebem. `postgres_app_password` é do
papel restrito `conforto_app`, com que `coletor` e `ict` conectam: o
`db-provision` (`scripts/provision-db-runtime.sh`) o cria ou atualiza a cada
subida com DML e sequências nos esquemas `public`, `historico` e
`dados_entrada`, sem DDL. Com `DB_EXIGIR_PAPEL_RESTRITO=1`, o processo só lê o
segredo do papel restrito e recusa conexão superusuária
(`app/nucleo/papel_do_banco.py`). O SharedAuth é
público: o build não precisa de credencial para instalá-lo.

Só se o host Windows intercepta HTTPS por antivírus ou proxy, e a autoridade
raiz correspondente está instalada no Windows, exporte a CA local usada pelo
build:

```powershell
.\scripts\exportar_ca_local.ps1
```

O arquivo `.certs/local-root-ca.crt` só é necessário nesse caso de inspeção
HTTPS, para que o build valide a cadeia apresentada pelo interceptador. O
secret BuildKit está marcado `required=false`, portanto o Compose e o build
funcionam sem o certificado em hosts sem inspeção TLS; não crie um arquivo
vazio. `docker compose --env-file .env.docker config --quiet` também funciona
sem esse arquivo.

## Pilha operacional

```powershell
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

O último comando verifica operações básicas no PostgreSQL da pilha. Para
acompanhar os processos:

```powershell
docker compose --env-file .env.docker logs -f ict coletor
```

## Qualidade

```powershell
docker compose --env-file .env.docker --profile quality run --build --rm quality
```

**`--build` não é opcional.** O serviço `quality` não monta o código do
host: o que ele executa é o que foi copiado para a imagem. `docker compose
run --build` reconstrói a partir do código atual, com cache: só as camadas
afetadas pela mudança são refeitas.

A suíte completa roda em paralelo com `pytest-xdist` (o `CMD` do estágio
`quality` passa `-n`). Cada worker cria o próprio banco (`conforto_teste_gw0`,
`_gw1`...; `conforto_teste_master` sem xdist), aplica nele a cadeia Alembic e o
apaga no fim. O banco é novo a cada execução, então a promessa de migrar um
banco vazio não depende de o `postgres-teste` ser recriado. Para iterar num
arquivo, passe o comando, e ele roda em série:
`docker compose --env-file .env.docker --profile quality run --build --rm quality pytest tests/test_x.py`.

### Imagens-base

Nem o `quality` nem o deploy buscam imagens-base novas por conta própria: o
Compose não declara `pull` nem `no_cache`. É a mesma regra do servidor, onde um
deploy comum monta sem `--pull` e só `deploy.sh conforto --refresh` busca bases
novas. Para testar bases novas na máquina antes do `--refresh`:

```powershell
docker compose --env-file .env.docker --profile quality build --pull --no-cache quality
docker compose --env-file .env.docker --profile quality run --build --rm quality
```

A CI semanal faz o mesmo build sem cache e com `--pull`, só como aviso.

O estágio `quality` instala as dependências de desenvolvimento e executa
`ruff check . && pytest`. Não documente uma contagem fixa de testes: a suíte
muda com o código.

O que merece teste, em que camada e em que forma está em `docs/TESTES.md`,
comum aos repositórios; leia antes de escrever ou remover um teste. Diante de
vermelho, decida de quem é o defeito antes de mexer: teste que mede texto
literal reprova mudança legítima, e nesse caso quem se corrige é a asserção.
Nunca escreva código para o teste passar.

A suíte tem duas camadas. A maior não abre conexão nenhuma (ver o docstring de
`tests/conftest.py`). A camada `banco` roda contra o `postgres-teste`, efêmero
e sem porta, que o `quality` sobe junto, com o schema criado pela cadeia
Alembic inteira. Ela serve ao que **só o PostgreSQL prova** -- comparação de
texto ISO como instante, `date_bin`/`date_trunc`, fuso, agregação por janela --
e não substitui os testes de domínio sem banco. Um teste nela é válido quando
um dublê não detectaria o defeito. No venv do host, sem `TESTE_DATABASE_URL`,
essa camada é pulada.

A CI também valida a configuração Compose, executa `pip-audit`, varre a imagem
servida com Trivy e confere contratos de segurança do runtime. Esses controles
não substituem o exercício do fluxo alterado nem a verificação da pilha.

## Triagem de alertas externos

O CodeQL roda pela configuração padrão do GitHub (Actions, JavaScript/TypeScript
e Python), sem workflow no repositório, e é check obrigatório no `main` ao lado
de `Qualidade` e `Runtime contracts`. Um alerta citado por ferramenta externa
deve ser associado a um arquivo e revisão concretos antes de virar mudança ou
supressão.

Também não há `rpcbind`, `portmap`, NFS ou serviço equivalente no `compose.yaml`.
Ruído desse tipo pertence ao host/VPS, não a esta composição. Não adicionar,
remover ou desabilitar pacotes/serviços sem inventário do ambiente e checagem de
dependências; a decisão atual é não modificar a aplicação.

## Validação proporcional

- documentação: `git diff --check`, links locais e busca por afirmações
  obsoletas;
- autenticação, autorização, sessão, CSRF e contratos cobertos: `quality` e
  exercício manual do fluxo afetado;
- persistência, dependências ou contêineres: `quality`, rebuild da pilha e
  `scripts.verificar_postgres`;
- schema: nova revisão Alembic, `upgrade` e `downgrade` coerentes, bootstrap em
  PostgreSQL vazio e backup conferido antes de tocar dados existentes;
- integração externa: teste controlado de falha, timeout e indisponibilidade.

Registre verificações não executadas e o motivo. O projeto valida software; não
descreva testes automatizados como validação experimental dos índices.

## Integridade e recuperação de dados

As revisões novas são aditivas. O histórico grava `timestamp_utc` e
`amostra_id` para deduplicação atômica; a leitura de timestamps legados sem
offset assume UTC. O job de dados de entrada grava medições em staging com uma
execução `processando`, renova um lease/heartbeat por lote e só publica a
execução quando ela passa a `concluida`. Leases expirados são recuperados e o
staging incompleto é descartado. Exports CSV também ignoram execuções não
concluídas.

A recuperação bloqueia a execução e revalida a expiração antes de apagar as
amostras. Se um heartbeat ou uma conclusão estiver em curso, aguarda seu commit
e preserva os dados quando a execução já tiver sido renovada ou concluída.

Alertas automáticos entram primeiro em `historico.notificacoes_outbox`. A chave
de deduplicação evita repetição do mesmo evento; o worker aplica retry com
limite, registra o último erro e recupera itens cujo bloqueio expirou. Uma
indisponibilidade SMTP não bloqueia o ciclo de leitura nem transforma falha de
envio em sucesso.

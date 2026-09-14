# ConfortoTermico — orientações de trabalho

> **Este projeto segue trilha própria e não faz parte da frota.** A frota é
> MegaSena, ControleBancario e ControleRendaVariavel; eles compartilham base e
> servem de referência uns aos outros. Aqui a **arquitetura é livre** — não
> compare com os irmãos nem proponha unificar por uniformidade. O que continua
> obrigatório é o **contrato operacional**: VPS, `deploy.sh`, vigia, autocura,
> alerta, backup, `SharedAuth` e as proteções de repositório. Decisão de
> 07/09/2026, registrada em
> [`docs/adr/008-trilha-propria-fora-da-frota.md`](docs/adr/008-trilha-propria-fora-da-frota.md).

## Escopo e fontes de verdade

Este é um software experimental de pesquisa, mantido e usado por uma pessoa.
Ele calcula, monitora e simula conforto térmico animal; hoje roda em modo
simulado e não aciona equipamentos físicos. Conectar hardware é um passo
previsto da pesquisa, com pré-requisitos: autorização explícita do mantenedor e
um plano de segurança para animais e equipamentos antes de desligar o modo
simulado.

As fórmulas, limites e combinações de espécie/índice têm fonte única em
`app/termico/thermal_indices.py`. Mudanças exigem justificativa, exemplos numéricos e
testes. Testes do código validam a implementação de software, não constituem
validação acadêmica ou experimental dos índices.

O ambiente suportado é Docker Compose com PostgreSQL. Leia `README.md` e os
documentos vivos em `docs/` antes de alterar comportamento documentado. Confirme
contratos no código, migrações, configuração e testes afetados.

## Arquitetura e invariantes

`ict` é a única interface pública: autentica, autoriza e encaminha comandos.
`coletor` é privado, mantém o ciclo por zona e expõe somente `/health` e
`/api/interno/*`. `criar_app_ict()` não deve importar cliente Modbus,
`zona_service` nem estado do coletor. O navegador consome somente a API do ICT.

Sessão, CSRF, limite de login, controle de acesso, hash de senha, senha
temporária e trava de troca pendente, destino pós-login seguro e a marca que
amarra a sessão à senha em vigor, cabeçalhos de
segurança, CSP e health checks vêm do SharedAuth. Perfis e áreas permanecem
próprios deste projeto em `app/seguranca/auth.py`. Preserve autorização no servidor; não
trate a ocultação de elementos da interface como controle de acesso.

Falhas de sensores ou atuadores devem ser observáveis sem derrubar processos.
Cada zona isola ciclo e estado. Entradas físicas inválidas não recebem fallback
silencioso. Estado transitório pertence ao coletor; dados persistentes passam
pelos módulos de banco.

PostgreSQL usa os schemas `historico` e `dados_entrada`. O job `schema` aplica
migrações Alembic antes de `ict` e `coletor`; a aplicação não cria schema em
runtime. Mudanças de schema usam nova revisão com `upgrade` e `downgrade`; não
reescreva revisão aplicada nem use `stamp` para declarar compatibilidade.

`app/nucleo/db_backend.py` é uma camada de compatibilidade de chamadas SQL sobre
PostgreSQL. A arquitetura é livre (ADR 008): se ela crescer a ponto de
atrapalhar, trocá-la por um ORM ou pelo driver direto é opção legítima. Ao
escrever SQL, evite ambiguidade entre
marcadores `?` e operadores JSONB: prefira `jsonb_exists(coluna, ?)`; considere
também que `%` literal precisa ser tratado ao adaptar para o estilo do psycopg.

## Segurança e dados

Segredos ficam em `.secrets/`, montados somente nos serviços que precisam
deles. Nunca os inclua em imagem, logs, documentação ou valores padrão. Senhas
ficam como hash; SMTP é write-only. Preserve a regra que impede remover ou
desativar o último administrador ativo.

Os contêineres operacionais usam usuário não-root, filesystem somente leitura,
capabilities removidas e diretórios temporários explícitos. Não monte código do
host, não exponha o coletor e não monte o socket Docker. Preserve health checks,
limites de logs, desligamento gracioso e respostas `/api/*` sem detalhes internos.

Medições de pesquisa podem ser descartadas quando a tarefa autorizar isso;
zonas, equipamentos, usuários e configurações devem ser preservados quando
possível. `docker compose down` preserva volumes. `down -v`, restauração e
migração destrutiva exigem autorização explícita, backup conferido e plano de
retorno. A proteção e o restore pertencem ao aplicativo BackupRestore, e o
procedimento operacional está em `docs/RUNBOOK.md`.

## Desenvolvimento e validação

Use as interfaces Docker documentadas pelo projeto para validar a imagem e o
Linux:

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
docker compose --env-file .env.docker --profile quality run --build --rm quality
```

`--build` faz parte do comando: o serviço `quality` não monta o código do
host e `docker compose run` só reconstrói quando a imagem não existe. Sem
ele, a validação roda a versão anterior do código e passa em verde.

### Loop rápido no host

O portão `quality` custa dezenas de segundos por rodada -- caro demais para o
ciclo de edição. Para isso existe um venv por projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

O `.venv/` é uma pasta do projeto, já ignorada pelo Git: não altera o Python
do sistema nem o PATH, e apagar a pasta desfaz a instalação por inteiro. A
proibição que vale é outra, e continua de pé -- nada de instalar dependências
do projeto no Python global do Windows.

`sharedauth` é instalado direto do GitHub, na tag que `pyproject.toml` fixa. O
repositório é **público**: o build precisa só de `git` no PATH, nenhuma
credencial.

Ao contrário dos três aplicativos da frota, este projeto **não** tem `uv.lock`
nem base fixada por digest — a fase F3 do levantamento não o cobriu, porque ele
segue trilha própria. Consequência prática: dois builds do mesmo commit ainda
podem resolver versões diferentes aqui. Se um dia isso incomodar, o caminho já
está percorrido nos irmãos.

Os dois ambientes acham defeitos diferentes, então nenhum substitui o outro.
O venv é Windows e já pegou travamento de suíte que o contêiner nunca mostrou
(ver o docstring de `tests/conftest.py`); o contêiner é Linux e é o único
lugar com `ruff` e `pip-audit` na versão que a CI usa. Itere no venv e passe
pelo `quality` antes de commitar.

Valide proporcionalmente ao risco e percorra manualmente o fluxo alterado.
Mudanças de persistência, migrações, dependências ou contêineres exigem a pilha
completa. Migração exige bootstrap em PostgreSQL vazio e backup conferido antes
de atuar sobre dados existentes. Registre verificações omitidas e o motivo.

A CI valida Compose, executa o estágio `quality`, audita dependências Python,
varre a imagem servida e confere contratos do runtime. Não afrouxe controles de
segurança para fazer a CI passar. Dependências usam faixas limitadas e são
atualizadas deliberadamente; preserve o menor piso efetivamente suportado.

Não altere contratos JSON isoladamente: atualize no mesmo trabalho o backend,
o consumidor JavaScript e a documentação pertinente.

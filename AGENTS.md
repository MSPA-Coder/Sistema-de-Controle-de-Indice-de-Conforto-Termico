# ConfortoTermico — guia de trabalho

<!-- comum: início. Cópia de _manutencao/compartilhados/AGENTS-comum.md; mude lá e rode sincronizar.py --aplicar. -->
## Regras comuns aos repositórios

**O que espera o "sim" do mantenedor:** commit e push (quando ele pedir),
deploy, qualquer ação no VPS, e apagar dados, volumes ou backups
(`docker compose down -v` inclusive). Na dúvida sobre algo irreversível,
pergunte; no resto, decida e diga o que decidiu.

**Ciclo.** Altere, rode a verificação completa deste repositório (seção
"Validação"), commite direto no `main` e dê `git push`: sem PR, sem push
forçado, sem rebase do `main` publicado. A CI roda depois, só como aviso, mas
vermelho no `main` se investiga. O Dependabot chega por PR, com merge manual. O
deploy é `~/deploy.sh <app>` no VPS1: monta a imagem a partir do `main`,
confere `/health` e volta sozinho se falhar. O VPS só espelha o `main`; nada se
edita lá. Imagem-base nova (correção do Debian ou do Python) só quando ele
pedir: testa na máquina e depois `~/deploy.sh <app> --refresh`. Ao terminar,
diga o que rodou, o resultado e o que deixou de validar.

**Dados e segredos.** Mudança destrutiva ou conversão de dados reais começa por
backup conferido no BackupRestore. Segredos ficam fora do Git (`.secrets/` ou
configuração do usuário) e não aparecem em código, imagem, log, diff,
documento nem relatório.

**Dependências.** Alargue o teto e preserve o piso já verificado: elevar o piso
afirma uma incompatibilidade, e isso exige prova. Vulnerabilidade se corrige
atualizando; exceção só explícita, com motivo e data. Enquanto o Dependabot não
aceitar Python 3.15, ele não propõe atualização de `uv` e o grafo do GitHub fica
parado no lock de 13/10/2026: confira alerta pela versão do `uv.lock`, e
atualize à mão (`uv lock --upgrade-package <pacote>`) quando o `pip-audit` ou o
Trivy apontarem.

**Testes.** `docs/TESTES.md` diz o que testar e como. Diante de vermelho,
decida de quem é o defeito; nunca escreva código para um teste passar. Não
rode duas verificações do mesmo repositório ao mesmo tempo: a segunda recria o
banco de teste e derruba a primeira.

**Cópias.** Este bloco, `docs/TESTES.md` e os arquivos listados em
`_manutencao/compartilhados/sincronizar.py` são cópias: mude a canônica lá e
rode `python compartilhados/sincronizar.py --aplicar` no `_manutencao`.

**Este arquivo.** Guarde aqui só o que o código não diz: limites, decisões com
o motivo, armadilhas e comandos. História fica no `git log`; decisão com
alternativas vira ADR; detalhe de implementação fica no código. Para
acrescentar uma regra, retire ou funda outra: `sincronizar.py` reprova este
arquivo acima de 900 palavras fora deste bloco.
<!-- comum: fim -->

## O sistema

Software experimental de pesquisa, mantido e usado por uma pessoa: calcula,
monitora e simula conforto térmico animal. No ar em
`https://conforto-mspa.duckdns.org` (deploy `~/deploy.sh conforto`; operação
em `docs/RUNBOOK.md`). Hoje roda em modo simulado e não aciona equipamento
físico. Ligar hardware exige autorização explícita do mantenedor e um plano de
segurança para animais e equipamentos antes de desligar o modo simulado.

**Trilha própria, fora da frota** (ADR 008): a arquitetura é livre; não compare
com o CB, o CRV ou o MegaSena nem proponha unificar por uniformidade. Continua
obrigatório o contrato operacional: VPS, `deploy.sh`, vigia, autocura, alerta,
backup e SharedAuth.

O `README.md` tem o índice de `docs/`; leia só o documento do assunto
(`docs/DOMINIO.md`, `docs/ARQUITETURA.md`, `docs/DESENVOLVIMENTO.md`,
`docs/SEGURANCA.md`, `docs/travas.md`, `docs/adr/`).

## Validação

```powershell
docker compose --env-file .env.docker --profile quality run --build --rm quality
```

Suíte em paralelo, com um banco de teste novo por worker e por execução. Rode
antes de todo commit de código.

- Persistência, migração, dependência ou contêiner: também a pilha completa
  (`up -d --build --wait`) e
  `docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres`.
- Mudança visível: percorra o fluxo na tela.
- Só documentação: `git diff --check` e
  `python ../_manutencao/compartilhados/sincronizar.py`.

## Limites

- Fórmulas, limites e combinações de espécie e índice têm fonte única em
  `app/termico/thermal_indices.py`. Mudança exige justificativa, exemplos
  numéricos e testes; os testes validam o software, não a validade acadêmica
  dos índices.
- `ict` é a única interface pública: autentica, autoriza e encaminha comandos.
  `coletor` é privado, mantém o ciclo por zona e expõe só `/health` e
  `/api/interno/*`; não se expõe nem se monta código do host nele.
  `criar_app_ict()` não importa cliente Modbus, `zona_service` nem estado do
  coletor; o navegador só fala com a API do ICT.
- Cada zona isola ciclo e estado. Falha de sensor ou atuador é observável sem
  derrubar processo, e entrada física inválida não recebe fallback silencioso.
- Contrato JSON muda junto com o backend, o JavaScript que o consome e a
  documentação, no mesmo trabalho.
- Sessão, CSRF, limite de login, senhas, cabeçalhos, CSP e health vêm do
  SharedAuth; perfis e áreas são deste projeto (`app/seguranca/auth.py`).
  Ocultar elemento na tela não é controle de acesso. Não se remove nem se
  desativa o último administrador ativo.
- PostgreSQL com os schemas `historico` e `dados_entrada`. O job `schema`
  aplica Alembic antes de `ict` e `coletor`; revisão nova com `upgrade` e
  `downgrade`, sem reescrever revisão aplicada nem usar `stamp`.
- Medições de pesquisa podem ser descartadas quando a tarefa autorizar; zonas,
  equipamentos, usuários e configurações se preservam.

## Armadilhas

- Não há `uv.lock`: as versões PyPI ficam em `constraints.txt` (runtime,
  ferramentas e isolamento de build), e o SharedAuth entra por referência Git
  imutável no `pyproject.toml`.
- `app/nucleo/db_backend.py` é uma camada de compatibilidade de SQL sobre o
  PostgreSQL; trocá-la por ORM ou driver direto é opção legítima se atrapalhar.
  Ao escrever SQL, prefira `jsonb_exists(coluna, ?)` ao operador `?` do JSONB e
  trate o `%` literal ao adaptar para o psycopg.
- Segredos ficam em `.secrets/`, montados só nos serviços que precisam; SMTP é
  só de escrita.

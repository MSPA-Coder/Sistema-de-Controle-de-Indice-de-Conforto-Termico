# ConfortoTermico — orientações de trabalho

## Escopo e fontes de verdade

Aplicação Flask para monitorar e controlar conforto térmico animal. As fórmulas
e limites científicos têm fonte única em `app/thermal_indices.py`; mudanças
exigem justificativa e exemplos numéricos testados. O ambiente operacional
suportado é Docker Compose com PostgreSQL, não SQLite nem execução nativa.

Confirme o contrato no código, migrações e testes afetados. Em seguida, consulte
`README.md` para instalação e arquitetura em operação, `docs/RUNBOOK.md` para
procedimentos e `docs/adr/` para decisões duráveis. Atualize documentação viva
junto com a mudança. Histórico de decisões, inclusive decisões substituídas,
fica em ADRs; não o replique aqui.

## Arquitetura e invariantes essenciais

`ict` é a única interface pública: autentica, autoriza e encaminha comandos
operacionais. `coletor` é privado, mantém Modbus e a malha por zona, e expõe
somente `/health` e `/api/interno/*`. `criar_app_ict()` não importa cliente
Modbus, `zona_service` nem estado do coletor. O navegador consome a API JSON do
ICT; a interface preserva CSRF e autorização no servidor.

Falhas de sensor ou atuador são observáveis e não derrubam os processos. Cada
zona isola seus ciclos e estados; parâmetros físicos inválidos não recebem
fallback silencioso. Persistência passa pelos módulos de banco e validação pela
fronteira. Mudanças de schema usam revisão Alembic nova, com upgrade e downgrade
coerentes, aplicável tanto a banco existente quanto novo; não reescreva revisão
aplicada, não use `stamp` como atalho e não adote bancos legados automaticamente.

Os schemas operacionais são `historico` e `dados_entrada`. A aplicação não
cria schema em runtime: o job `schema` aplica as migrações controladamente antes
de `ict` e `coletor`. Dados de configuração e controle ficam no PostgreSQL;
estado transitório pertence ao coletor, não a globals compartilhados.

## Segurança, implantação e riscos destrutivos

Segredos ficam em `.secrets/`, montados apenas nos serviços que precisam deles;
nunca os inclua em imagem, logs, respostas ou valores padrão. A chave de sessão
persistida no volume e a justificativa de seu fallback estão registradas na ADR
correspondente. Senhas ficam como hash e SMTP é write-only. Preserve a regra de
que o último administrador ativo não pode ser removido ou desativado.

Os contêineres operacionais usam imagem construída, usuário não-root, filesystem
somente leitura, capabilities removidas e diretórios temporários explícitos.
Não monte código do host nem exponha o coletor. Preserve health checks, limites
de logs e desligamento gracioso. Respostas `/api/*` não expõem exceções, SQL,
caminhos ou credenciais.

`docker compose down` preserva volumes; `down -v`, restaurações e migrações
destrutivas exigem autorização explícita, backup validado e plano de retorno.
Não imprima ou altere segredos. O runbook define backup e recuperação.

## Operação e validação proporcional

Use somente Docker Compose para ferramentas do projeto. A sequência operacional
atual é:

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

O estágio Docker `quality` instala as dependências de desenvolvimento e executa
`ruff check . && pytest`; ele contém a suíte mínima de cinco testes de segurança
e fumaça. A CI do GitHub valida a configuração Compose e executa esse mesmo
estágio em imagem limpa; não há suíte ampla, cobertura, Mypy nem `pip-audit`
dentro da imagem.
Execute a qualidade em mudanças de acesso, sessão, CSRF, autorização ou código
que ela cubra:

```powershell
docker compose --env-file .env.docker --profile quality run --rm quality
```

Além dos controles automáticos, percorra manualmente o fluxo alterado. Mudanças
em persistência, migrações, dependências ou contêineres exigem a pilha completa
e `scripts.verificar_postgres`; schema exige bootstrap em PostgreSQL vazio e
backup validado antes de atuar sobre dados existentes. Documente controles
omitidos e o motivo.

## Implantação em produção

O sistema roda em um VPS Oracle atrás de Nginx com TLS, em
`https://conforto-mspa.duckdns.org`, a partir de
`/home/ubuntu/apps/conforto-termico`.

O código do servidor é espelho do `main`, em sentido único: desenvolvimento na
máquina local, commit, push ao GitHub, e só então implantação. **Não edite
código, não commite e não faça merge no VPS** — `~/deploy.sh conforto` aborta ao
encontrar árvore suja, e a *deploy key* do servidor é somente leitura, então um
push de lá falharia de qualquer forma. Ver `docs/adr/006-implantacao-vps.md`.

`.secrets/` (`postgres_password.txt`, `internal_token.txt`) e `.certs/` não são
versionados e vivem apenas no servidor; um reclone precisa restaurá-los, ou o
build falha e o banco fica inacessível. Os dados ficam nos volumes
`conforto-termico_postgres_data` e `conforto-termico_app_instance`, fora da
pasta do código: substituir o diretório do projeto não os afeta. A base do VPS é
independente da local. Consulte `docs/deployment-vps.md` antes de qualquer
operação no VPS.

## Evolução de versões e compatibilidade

**Faixas de dependência: alargue o teto, mantenha o piso.** O Dependabot roda
com `versioning-strategy: widen`. Quando ele propuser elevar o mínimo, aproveite
apenas a parte que alarga o teto e recuse a que sobe o piso. O piso registra a
compatibilidade mínima efetivamente verificada, não a versão mais nova
disponível: elevá-lo declara uma incompatibilidade que ninguém comprovou e não
muda nada do que é instalado, porque o pip já resolve para a versão mais nova
permitida pela faixa.


Dependências usam faixas limitadas e são atualizadas deliberadamente. Atualização
patch deve passar pela validação proporcional; atualização menor ou maior exige
compatibilidade confirmada com Python, PostgreSQL, Flask, Docker e a separação
ICT/coletor, seguida de rebuild limpo e execução de `quality`. Quebra de API
JSON, schema, segredo ou operação exige decisão explícita em ADR, consumidores
atualizados, migração/rollback e revisão Alembic quando persistente. Mantenha
compatibilidade apenas enquanto houver consumidor conhecido.

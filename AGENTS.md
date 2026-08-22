# ConfortoTermico — orientações de trabalho

## Escopo e fontes de verdade

Este é um software experimental de pesquisa, mantido e usado por uma pessoa.
Ele calcula, monitora e simula conforto térmico animal; ainda não está em uso
operacional e não aciona equipamentos físicos. Não desabilite o modo simulado
nem conecte hardware como parte de uma tarefa sem autorização explícita e um
plano de segurança próprio.

As fórmulas, limites e combinações de espécie/índice têm fonte única em
`app/thermal_indices.py`. Mudanças exigem justificativa, exemplos numéricos e
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

Sessão, CSRF, limite de login, controle de acesso, hash de senha, cabeçalhos de
segurança, CSP e health checks vêm do SharedAuth. Perfis e áreas permanecem
próprios deste projeto em `app/auth.py`. Preserve autorização no servidor; não
trate a ocultação de elementos da interface como controle de acesso.

Falhas de sensores ou atuadores devem ser observáveis sem derrubar processos.
Cada zona isola ciclo e estado. Entradas físicas inválidas não recebem fallback
silencioso. Estado transitório pertence ao coletor; dados persistentes passam
pelos módulos de banco.

PostgreSQL usa os schemas `historico` e `dados_entrada`. O job `schema` aplica
migrações Alembic antes de `ict` e `coletor`; a aplicação não cria schema em
runtime. Mudanças de schema usam nova revisão com `upgrade` e `downgrade`; não
reescreva revisão aplicada nem use `stamp` para declarar compatibilidade.

`app/db_backend.py` é apenas uma camada de compatibilidade de chamadas SQL sobre
PostgreSQL. Não amplie sua superfície. Ao escrever SQL, evite ambiguidade entre
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
retorno. O procedimento e as limitações do backup interno estão em
`docs/RUNBOOK.md`.

## Desenvolvimento e validação

Use somente as interfaces Docker documentadas pelo projeto:

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
docker compose --env-file .env.docker --profile quality run --rm quality
```

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

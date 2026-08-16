# Runbook operacional

O único ambiente operacional suportado é Docker Compose com PostgreSQL.

## Início e verificação

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

O ICT é a interface pública em `http://127.0.0.1:5000`. O coletor não expõe
porta no host; investigue seu estado por `docker compose ... logs coletor`.

## Diagnóstico

```powershell
docker compose --env-file .env.docker logs --tail=100 ict
docker compose --env-file .env.docker logs --tail=100 coletor
docker compose --env-file .env.docker logs --tail=100 postgres
docker compose --env-file .env.docker ps
```

Não altere nem imprima segredos em `.secrets/`. Alterações de ambiente exigem
recriar os serviços afetados. A aplicação só deve operar após o serviço
`schema` concluir as migrações Alembic. O coletor é privado: use os logs e o
health check do Compose para diagnosticá-lo, nunca uma porta exposta no host.

## Backup e recuperação

Use a função autenticada da área Sistema para gerar um dump, ou execute
`pg_dump` no serviço PostgreSQL com credenciais concedidas por segredo. Antes
de qualquer restauração ou migração destrutiva, valide um backup e planeje a
janela de manutenção. A instalação suportada começa em banco novo por
`alembic upgrade head`; não use `alembic stamp` para declarar compatível um
banco sem histórico Alembic compatível.

## Parada planejada

```powershell
docker compose --env-file .env.docker down
```

Esse comando preserva o volume PostgreSQL. `down -v` remove dados persistentes
e só pode ser usado quando essa remoção tiver sido deliberadamente autorizada.

## Verificação estática

O projeto não mantém CI nem suíte ampla de regressão automatizada; a decisão e
seu histórico estão em `docs/adr/003-ci-cd-pipeline.md` e
`docs/adr/004-qualidade-codigo-ferramentas.md`. O que permanece é a suíte
mínima de segurança e fumaça mais o Ruff, ambos no estágio `quality` da imagem:

```powershell
docker compose --env-file .env.docker --profile quality run --rm quality
```

Mudanças que tocam autenticação, autorização, CSRF ou sessão sempre executam
esse comando — é ele quem roda os 5 testes de `tests/`, não só o lint.
Mudanças relevantes são verificadas manualmente no fluxo afetado. Mudanças de
schema exigem, além disso, bootstrap em PostgreSQL vazio por
`alembic upgrade head`.

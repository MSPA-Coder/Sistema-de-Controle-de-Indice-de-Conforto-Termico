# Runbook operacional

O único ambiente operacional suportado é Docker Compose com PostgreSQL.

## Início e verificação

```powershell
docker compose --env-file .env.docker up -d --build
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
`schema` concluir as migrações Alembic.

## Backup e recuperação

Use a função autenticada da área Sistema para gerar um dump, ou execute
`pg_dump` no serviço PostgreSQL com credenciais concedidas por segredo. Antes
de qualquer restauração ou migração destrutiva, valide um backup e planeje a
janela de manutenção. Bancos legados sem `alembic_version` não são adotados
automaticamente: exigem verificação estrutural, backup validado e registro
administrativo explícito da revisão.

## Testes

```powershell
docker compose -f compose.test.yaml --profile tools build test
docker compose -f compose.test.yaml up -d --wait postgres_teste
docker compose -f compose.test.yaml --profile tools run --rm test
docker compose -f compose.test.yaml down --volumes
```

O banco de teste usa `tmpfs`, `CONFORTO_TESTING=1` e o nome fixo
`conforto_termico_teste`; a suíte recusa truncar outro alvo.

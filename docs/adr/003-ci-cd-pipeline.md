# ADR 003: validação contínua em contêineres

## Status

Aceito.

## Decisão

O workflow em `.github/workflows/ci.yml` executa em `main` e em pull requests
para `main`. Ele constrói a imagem `quality`, inicia PostgreSQL descartável e
executa Ruff, Mypy, a suíte `unittest` e o relatório de cobertura pelo serviço
`test` do Docker Compose.

Falhas são bloqueantes: a CI não usa `|| true`, não roda ferramentas do
projeto no host e sempre remove a infraestrutura de teste ao final.

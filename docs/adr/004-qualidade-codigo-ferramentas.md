# ADR 004: Ferramentas de qualidade na imagem dedicada

## Status

Aceito, com escopo reduzido. A imagem operacional continua separada do estágio
`quality`; o conjunto atual de ferramentas é Ruff e pytest, não Mypy ou
Coverage.

## Contexto

A imagem `runtime` serve `schema`, `ict` e `coletor` e não deve carregar
ferramentas de desenvolvimento. A decisão original incluía Mypy, Coverage,
serviço `test` e `compose.test.yaml`; eles foram removidos quando a validação
foi reduzida para o uso individual. Esse histórico explica o escopo, mas não é
um procedimento atual.

## Decisão

`requirements.txt` define dependências de execução. `requirements-dev.txt` é
instalado somente no estágio Docker `quality`, sobre as dependências de runtime.
O estágio copia `pyproject.toml` e `tests/`, configura caches em `/tmp` e roda:

```sh
ruff check . && pytest
```

O serviço `quality` do `compose.yaml` aponta para esse estágio e fica atrás do
perfil `quality`; ele não é iniciado junto com a operação normal.

## Consequências

- A imagem operacional permanece menor e sem ferramentas de qualidade.
- Ruff e a suíte mínima de segurança/fumaça são reproduzíveis sem Python no
  host e devem ser chamados por `docker compose --profile quality run --rm quality`.
- A ausência de Mypy, Coverage e suíte ampla é deliberada, não uma indicação de
  que pytest tenha sido removido.
- A validação de PostgreSQL continua na pilha operacional e não é substituída
  por esse estágio.

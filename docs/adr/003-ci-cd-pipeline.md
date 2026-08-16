# ADR 003: Validação contínua em contêineres

## Status

Substituída em parte. O projeto não mantém CI, workflow GitHub, suíte ampla de
regressão, cobertura, Mypy ou auditoria de dependências. A decisão histórica de
executar ferramentas no host também continua rejeitada: os controles atuais
ficam no estágio Docker `quality` e são chamados manualmente pelo Compose.

## Contexto

O projeto é desenvolvido e operado com Docker Compose. Ferramentas no host
introduzem diferenças de versão e deixam a validação desconectada da imagem que
executa o código. A antiga decisão previa CI, `compose.test.yaml`, serviço
`test`, PostgreSQL descartável e anéis extensos; esses artefatos foram
removidos como simplificação deliberada para uso individual.

## Decisão atual

A validação automática mínima é executada no contêiner `quality`:

```powershell
docker compose --env-file .env.docker --profile quality run --rm quality
```

O Dockerfile instala as dependências de desenvolvimento nesse estágio e executa
`ruff check . && pytest`. A validação operacional permanece separada e usa a
pilha real: `docker compose ... up -d --build --wait`, seguida de
`docker compose ... exec ict python -m scripts.verificar_postgres`.

## Consequências

- Não há verificação automática em pull request ou push; quem altera o projeto
  executa a validação proporcional e registra controles omitidos.
- Mudanças de acesso executam `quality`; mudanças de persistência, contêiner ou
  dependência também sobem a pilha e verificam PostgreSQL.
- Migrações continuam exigindo backup validado e bootstrap por Alembic em banco
  PostgreSQL vazio.
- A antiga decisão permanece neste ADR como contexto, mas não descreve mais
  arquivos ou comandos disponíveis.

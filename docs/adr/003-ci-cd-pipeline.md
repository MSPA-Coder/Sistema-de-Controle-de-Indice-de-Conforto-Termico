# ADR 003: Validação contínua em contêineres

## Status

Parcialmente retomada em 2026-08-16. A decisão histórica de não manter CI foi
substituída apenas por uma automação mínima no GitHub. O projeto continua sem
suíte ampla de regressão, cobertura, Mypy ou `pip-audit` dentro da imagem. A
decisão histórica de executar ferramentas no host também continua rejeitada:
os controles usam a imagem Docker do projeto.

## Contexto

O projeto é desenvolvido e operado com Docker Compose. Ferramentas no host
introduzem diferenças de versão e deixam a validação desconectada da imagem que
executa o código. A decisão anterior de remover CI, `compose.test.yaml`,
serviço `test`, PostgreSQL descartável e anéis extensos foi uma simplificação
deliberada para uso individual.

Essa simplificação não elimina o risco de integrar mudança não construída ou
que falhe na suíte mínima. A retomada é limitada para manter o mesmo ambiente:
o workflow só valida a configuração Compose e constrói/executa o estágio
`quality`; não sobe a pilha completa nem usa dados, credenciais ou CA reais.

## Decisão atual

A validação automática mínima é executada no contêiner `quality`:

```powershell
docker compose --env-file .env.docker --profile quality run --rm quality
```

O Dockerfile instala as dependências de desenvolvimento nesse estágio e executa
`ruff check . && pytest`. `.github/workflows/ci.yml` chama esse estágio após
`docker compose config --quiet`, em push e pull request para `main`, por
despacho manual e em agenda semanal. As entradas exigidas pelo Compose são
artefatos fictícios e efêmeros do runner. Dependabot verifica semanalmente os
ecossistemas pip, Docker e GitHub Actions e agrupa atualizações minor/patch.

A validação operacional permanece separada e usa a pilha real:
`docker compose ... up -d --build --wait`, seguida de
`docker compose ... exec ict python -m scripts.verificar_postgres`.

## Consequências

- Push e pull request para `main` recebem a verificação mínima do Compose e
  `quality`; a concorrência cancela execuções ultrapassadas da mesma referência.
- Quem altera o projeto continua responsável pela validação proporcional e por
  registrar controles omitidos, especialmente os que exigem a pilha completa.
- Mudanças de acesso executam `quality`; mudanças de persistência, contêiner ou
  dependência também sobem a pilha e verificam PostgreSQL.
- Migrações continuam exigindo backup validado e bootstrap por Alembic em banco
  PostgreSQL vazio.
- A decisão anterior permanece registrada neste ADR como contexto; a retomada
  não recria `compose.test.yaml`, serviço `test`, cobertura ou CI de implantação.

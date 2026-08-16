# ADR 002: PostgreSQL como único banco operacional e de persistência em testes

## Status

Aceito.

## Decisão

O projeto utiliza PostgreSQL 17 nos schemas `historico` e `dados_entrada`.
Schema novo é criado exclusivamente por `alembic upgrade head`; a aplicação
não cria tabelas nem adota bancos legados automaticamente. SQLite não é
backend suportado para a aplicação ou para testes de persistência. Não há
fluxo de adoção de banco sem histórico Alembic compatível no repositório.

## Consequências

- Conexões exigem a configuração PostgreSQL do Compose.
- Mudanças de schema usam revisões Alembic novas, com `upgrade` e `downgrade`,
  e são validadas por bootstrap em PostgreSQL vazio. O serviço descartável de
  `compose.test.yaml` citado na versão original desta ADR foi removido junto
  com a suíte ampla de regressão; o controle mínimo atual está registrado nas
  ADRs 003 e 004.
- Um banco sem histórico Alembic compatível não deve receber `alembic stamp`
  como atalho de instalação, atualização ou validação.

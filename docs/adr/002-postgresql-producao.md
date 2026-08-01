# ADR 002: PostgreSQL como único banco operacional e de persistência em testes

## Status

Aceito.

## Decisão

O projeto utiliza PostgreSQL 17 nos schemas `historico` e `dados_entrada`.
Schema novo é criado exclusivamente por `alembic upgrade head`; a aplicação
não cria tabelas nem adota bancos legados automaticamente. SQLite não é
backend suportado para a aplicação ou para testes de persistência.

## Consequências

- Conexões exigem a configuração PostgreSQL do Compose.
- Testes com persistência executam somente no serviço descartável de
  `compose.test.yaml`, com proteção explícita contra `TRUNCATE` no banco
  operacional.
- Mudanças de schema usam revisões Alembic novas, com `upgrade` e `downgrade`.
- Adoção de banco legado requer backup validado, auditoria estrutural e ação
  administrativa registrada.

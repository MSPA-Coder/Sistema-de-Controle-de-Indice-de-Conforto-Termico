# ADR 002: PostgreSQL como Banco de Dados de Produção

## Status
Aceito

## Contexto
O sistema requer persistência robusta para histórico de leituras, configurações de zonas, usuários e dados de entrada. Inicialmente usava SQLite para simplicidade nos testes, mas produção exige concorrência, confiabilidade e recursos enterprise.

## Decisão
Adotar PostgreSQL 17 como banco de dados de produção, mantendo SQLite apenas para testes unitários rápidos quando DATABASE_URL não está definida.

### Configuração
- URL via variável `DATABASE_URL` ou construção a partir de `DB_HOST`, `DB_USER`, `DB_PASSWORD_FILE`, `DB_PORT`, `DB_NAME`
- Connection pooling com SQLAlchemy (pool_size=5, max_overflow=10, pool_recycle=1800)
- Schema dedicado para isolamento
- Alembic para migrações

## Consequências
### Positivas
- Concorrência robusta com MVCC
- Confiabilidade e durabilidade ACID
- Recursos avançados (índices, views materializadas, JSONB)
- Backup e replication nativos
- Escalabilidade vertical e horizontal

### Negativas
- Complexidade operacional aumentada
- Dependência de serviço externo (container PostgreSQL)
- overhead de conexão mitigado por pooling

## Alternativas Consideradas
1. **SQLite em produção**: Rejeitado - lock de escrita único, sem concorrência real
2. **MySQL/MariaDB**: Considerado - PostgreSQL oferece mais recursos avançados
3. **NoSQL (MongoDB)**: Rejeitado - dados altamente relacionais exigem SQL

## Implementação
- `app/db_backend.py`: Backend PostgreSQL compatível com interface SQLite
- `app/database.py`: Camada de domínio usando backend abstrato
- Migrations em `migrations/versions/`

## Referências
- AGENTS.md - Migração SQLite → PostgreSQL
- compose.yaml - Configuração do serviço PostgreSQL

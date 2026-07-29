# Runbook Operacional - Sistema de Conforto Térmico Animal

## Visão Geral

Este runbook fornece procedimentos para operação, troubleshooting e recuperação do sistema em produção.

## Arquitetura

- **ICT (Interface de Conforto Térmico)**: Aplicação Flask pública (porta 8080)
- **Coletor**: Serviço privado Modbus (porta 8081, não exposto)
- **PostgreSQL**: Banco de dados (porta 5432)

## Procedimentos de Inicialização

### Start Completo

```bash
# Iniciar todos os serviços
docker compose up -d

# Verificar status
docker compose ps

# Ver logs em tempo real
docker compose logs -f
```

### Start Individual

```bash
# Apenas ICT
docker compose up -d ict

# Apenas Coletor
docker compose up -d coletor

# Apenas PostgreSQL
docker compose up -d postgres
```

## Health Checks

### Endpoint HTTP

```bash
curl http://localhost:8080/health
# Esperado: {"status": "ok"}
```

### Verificar Conexão com Banco

```bash
docker compose exec postgres psql -U thermal_user -d thermal_db -c "SELECT 1;"
```

### Verificar Coletor

```bash
# De dentro do container ICT
docker compose exec ict python -c "from app.ict.coletor_client import testar_conexao; print(testar_conexao())"
```

## Troubleshooting Comum

### 1. ICT Não Responde

**Sintoma:** HTTP 502/503 ou timeout

**Diagnóstico:**
```bash
# Verificar se container está rodando
docker compose ps ict

# Ver logs de erro
docker compose logs --tail=100 ict

# Verificar uso de memória/CPU
docker stats ict
```

**Solução:**
```bash
# Restart do serviço
docker compose restart ict

# Se persistir, rebuild
docker compose build ict
docker compose up -d ict
```

### 2. Erros de Banco de Dados

**Sintoma:** Logs com "connection refused" ou "authentication failed"

**Diagnóstico:**
```bash
# Verificar se PostgreSQL está up
docker compose ps postgres

# Ver logs do postgres
docker compose logs --tail=100 postgres

# Testar conexão
docker compose exec postgres pg_isready -U thermal_user -d thermal_db
```

**Solução:**
```bash
# Restart do postgres
docker compose restart postgres

# Verificar variáveis de ambiente
docker compose exec ict env | grep -E "DB_|DATABASE"
```

### 3. Coletor Não Comunica

**Sintoma:** Leituras não atualizam, última leitura antiga

**Diagnóstico:**
```bash
# Ver status do coletor
docker compose ps coletor

# Ver logs do coletor
docker compose logs --tail=100 coletor

# Testar conectividade interna
docker compose exec ict curl -s http://coletor:8081/health
```

**Solução:**
```bash
# Restart do coletor
docker compose restart coletor

# Verificar configuração Modbus
docker compose exec ict cat /app/.secrets/modbus_config.json
```

### 4. Performance Degradada

**Sintoma:** Requests lentos, timeouts

**Diagnóstico:**
```bash
# Verificar queries lentas no postgres
docker compose exec postgres psql -U thermal_user -d thermal_db -c \
  "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"

# Verificar locks
docker compose exec postgres psql -U thermal_user -d thermal_db -c \
  "SELECT * FROM pg_locks WHERE NOT granted;"

# Verificar conexões ativas
docker compose exec postgres psql -U thermal_user -d thermal_db -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

**Solução:**
```bash
# Analisar tabela de leituras
docker compose exec postgres psql -U thermal_user -d thermal_db -c \
  "ANALYZE leituras;"

# Vacuum em tabelas grandes
docker compose exec postgres psql -U thermal_user -d thermal_db -c \
  "VACUUM ANALYZE leituras;"
```

## Backup e Restore

### Backup Manual

```bash
# Backup completo do banco
docker compose exec postgres pg_dump -U thermal_user thermal_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Backup via endpoint ICT (se disponível)
curl -X POST http://localhost:8080/admin/backup -H "Cookie: session=..." -o backup.sql
```

### Restore

```bash
# Restaurar backup
cat backup.sql | docker compose exec -T postgres psql -U thermal_user -d thermal_db

# Verificar integridade
docker compose exec postgres psql -U thermal_user -d thermal_db -c \
  "SELECT count(*) FROM usuarios;"
```

## Escalonamento

### Aumentar Recursos

```yaml
# docker-compose.override.yaml
services:
  ict:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### Horizontal Scaling (ICT)

```bash
# Scale para 3 réplicas
docker compose up -d --scale ict=3

# Requer load balancer externo (nginx, traefik)
```

## Rollback de Deploy

### Reverter para Versão Anterior

```bash
# Listar imagens disponíveis
docker images thermal-ict

# Fazer checkout do commit anterior
git checkout <commit-anterior>

# Rebuild e redeploy
docker compose build
docker compose up -d
```

### Rollback de Migração de Banco

```bash
# Listar migrações
docker compose exec ict alembic history

# Reverter última migração
docker compose exec ict alembic downgrade -1

# Reverter para versão específica
docker compose exec ict alembic downgrade <revision>
```

## Monitoramento

### Métricas para Observar

1. **Latência de Request**: < 200ms p95
2. **Taxa de Erro**: < 1%
3. **Uso de CPU**: < 70% sustentado
4. **Uso de Memória**: < 80%
5. **Conexões PostgreSQL**: < 80% do max
6. **Idade da Última Leitura**: < 5 minutos

### Logs Estruturados

```bash
# Buscar erros nos últimos 10 minutos
docker compose logs --since=10m ict | grep -i error

# Exportar logs para análise
docker compose logs --since=1h ict > logs_ict_$(date +%Y%m%d_%H%M%S).txt
```

## Contato e Escalation

1. **Nível 1**: Verificar este runbook
2. **Nível 2**: Acionar equipe de operações
3. **Nível 3**: Acionar desenvolvedores do sistema

## Checklist de Incidente

- [ ] Identificar sintoma e impacto
- [ ] Verificar health checks
- [ ] Consultar logs recentes
- [ ] Isolar componente afetado
- [ ] Aplicar procedimento de recuperação
- [ ] Validar restauração do serviço
- [ ] Documentar causa raiz
- [ ] Criar ticket de follow-up

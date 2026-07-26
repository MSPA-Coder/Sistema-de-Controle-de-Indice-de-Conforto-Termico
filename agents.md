# Diretrizes para agentes de código

## Fonte de verdade

Este repositório é uma aplicação Flask para cálculo e controle de conforto
térmico animal. Antes de alterar uma área, confirme o contrato no código, nas
migrações e nos testes atuais. Documentos históricos explicam contexto, mas não
se sobrepõem ao comportamento executável.

O único ambiente operacional suportado é Docker Compose com PostgreSQL.
SQLite é um backend deliberadamente limitado à suíte unitária em memória ou em
diretórios temporários. Não acrescente compatibilidade de produção com SQLite,
execução Windows nativa ou bancos legados sem um requisito atual verificável.

## Verificação

Execute no mínimo:

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker build schema
docker run --rm -e DATABASE_URL= conforto-termico:local python -m unittest discover -v
docker compose --env-file .env.docker up -d
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

Use testes direcionados durante o desenvolvimento. Mudanças em persistência,
migrações, segurança ou implantação exigem a suíte completa e uma validação na
pilha real. Testes Modbus usam fakes ou simulação, nunca hardware real.

## Arquitetura e contratos

- `ict` é a única interface pública. Autentica, autoriza e encaminha comandos
  operacionais pela API interna.
- `coletor` é privado. Possui Modbus, estado da malha e somente `/health` e
  `/api/interno/*`.
- `criar_app_ict()` não importa `app.modbus_client`, `app.zona_service` nem
  estado do coletor.
- A autorização é aplicada no servidor. A interface apenas reflete permissões.
- Falhas de sensor ou atuador ficam observáveis e não derrubam o processo.
- Ciclos e estados de controle são isolados por zona; parâmetros físicos
  inválidos nunca recebem fallbacks silenciosos.
- Fórmulas e limites científicos têm fonte única em `app/thermal_indices.py`.
  Mudanças exigem justificativa e exemplos numéricos testados.
- Persistência passa pelos módulos de banco; diferenças SQLite/PostgreSQL ficam
  no adaptador. Dados são validados na fronteira.
- Toda alteração de esquema usa Alembic, com `upgrade` e `downgrade`
  coerentes. O identificador de revisão tem no máximo 32 caracteres e a
  migração deve funcionar tanto em banco existente quanto em instalação nova.

## Implantação e segurança

- Segredos ficam em `.secrets/` e são montados pelo Compose; nunca inclua
  valores padrão, segredos em imagens, logs ou respostas.
- Os contêineres da aplicação executam sem root, com filesystem somente leitura,
  capabilities removidas e diretórios temporários explícitos.
- Não monte o código do host em serviços operacionais. A imagem construída é o
  artefato executado por `ict`, `coletor` e tarefas administrativas.
- Preserve health checks, limites de logs e desligamento gracioso.
- Respostas `/api/*` não expõem exceções, SQL, caminhos nem credenciais.
- Senhas de usuários ficam somente como hash; senha SMTP é write-only.
- O último administrador ativo não pode ser removido ou desativado.
- Requisições mutáveis do navegador usam proteção CSRF.

## Prática de mudança

Prefira testes de comportamento e risco real a testes de detalhes internos.
Quando um requisito mudar, atualize ou remova o teste antigo; não preserve código
sem consumidor apenas para mantê-lo verde. Uma quebra intencional é aceitável
quando consumidores, migração, testes e documentação são tratados juntos.

Use UTF-8 sem BOM, português do Brasil para textos de usuário e identificadores
ASCII. Preserve alterações locais não relacionadas.

Atualize o `README.md` quando instalação, configuração, operação, arquitetura,
segurança ou limitações mudarem. Documente somente o estado atual, sem narrar
tentativas, rodadas de migração ou bugs já resolvidos.

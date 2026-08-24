# Operação, dados e recuperação

O ambiente suportado é Docker Compose com PostgreSQL. O uso é individual,
experimental e simulado, tanto localmente quanto na instância de demonstração
do VPS; não conecte equipamentos físicos.

## Iniciar e diagnosticar localmente

```powershell
docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up -d --build --wait
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

O ICT fica em `http://127.0.0.1:5001`. O coletor é privado e deve ser observado
pelos health checks e logs:

```powershell
docker compose --env-file .env.docker logs --tail=100 ict coletor postgres
docker compose --env-file .env.docker ps
```

O serviço `schema` precisa terminar com sucesso antes de `ict` e `coletor`.
Mantenha `CONFORTO_DEBUG=0` fora de desenvolvimento local. Não imprima nem
altere segredos durante o diagnóstico.

Para parar preservando os volumes:

```powershell
docker compose --env-file .env.docker down
```

## Dados persistentes

- `postgres_data`: usuários, zonas, equipamentos, configurações, medições,
  agregados, eventos e dados de entrada;
- `app_instance`: arquivos locais de suporte ao runtime, quando habilitados;
- `.secrets/`: arquivos locais necessários ao Compose, fora dos volumes e do Git.

O schema `historico` reúne configuração e dados operacionais. O schema
`dados_entrada` reúne configurações e séries geradas para pesquisa. Excluir o
histórico pela interface remove leituras e seus derivados, mas preserva zonas,
equipamentos, usuários e configurações. Dados gerados podem ser excluídos
separadamente.

Medições de pesquisa podem ser descartadas. Preserve usuários, zonas,
equipamentos e configurações sempre que possível. Um dump do banco completo
preserva tanto essas configurações quanto as medições existentes.

## Proteção central com BackupRestore

O mecanismo preferido é o projeto irmão
[BackupRestore](https://github.com/MSPA-Coder/BackupRestore). Ele cobre:

- `conforto_termico`: dump completo e ZIP do código da instância local;
- `conforto_termico_vps`: dump completo produzido no VPS e sincronizado pelo
  canal restrito.

O BackupRestore verifica os artefatos antes de catalogá-los, registra SHA-256 e
origem, aplica retenção somente depois de haver substituto válido e oferece
ensaio de restauração no PostgreSQL descartável `backuprestore-sandbox`. O
restore do ConfortoTermico já foi ensaiado. Consulte o README e
`RESTAURAR.md` daquele projeto para operação e recuperação; não reproduza aqui
comandos que possam divergir da ferramenta central.

## Recuperação

Esta aplicação não possui rota, botão ou integração interna de restauração. A
proteção e os ensaios pertencem ao projeto BackupRestore; a recuperação real
deve seguir o `RESTAURAR.md` dele. Não a improvise pela interface deste app.

Antes de restaurar:

1. preserve o estado atual;
2. valide o artefato e o restore no sandbox do BackupRestore;
3. confirme a compatibilidade entre o código e a revisão Alembic do dump;
4. planeje a parada de `ict` e `coletor` e o retorno;
5. confirme a preservação de usuários, zonas, equipamentos e configurações.

Uma restauração sobre o banco corrente pode substituir configurações, usuários
e medições. Não use `alembic stamp` para mascarar incompatibilidade.
`down -v` e `down --volumes` removem dados persistentes e exigem autorização
explícita.

## Instância no VPS

A instância em `https://conforto-mspa.duckdns.org` é pesquisa/demonstração, não
uso operacional nem homologação física. O Nginx termina TLS e encaminha ao ICT
em `127.0.0.1:5401`; o PostgreSQL fica em `127.0.0.1:5402`; o coletor não é
exposto no host. Código e dados são independentes: os volumes Docker persistem
fora de `/home/ubuntu/apps/conforto-termico`.

O deploy oficial vem de `_manutencao/vps/deploy.sh` e está instalado como
`~/deploy.sh`:

```bash
~/deploy.sh conforto --check
~/deploy.sh conforto
~/deploy.sh --status
```

Não edite nem commite no VPS. O script exige checkout limpo, avança a partir do
`main`, reconstrói a imagem e valida o endereço público. Se a nova versão não
ficar saudável, ele restaura o commit e a imagem anteriores. Esse rollback
**não reverte migrações**; mudança de schema exige compatibilidade, backup
central conferido pelo BackupRestore e procedimento explícito de recuperação de dados.

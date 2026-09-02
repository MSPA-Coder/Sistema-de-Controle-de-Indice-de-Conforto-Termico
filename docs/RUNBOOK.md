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

## Manutenção e auditoria

**Atualizar agregados pendentes**, na aba Sistema, é manutenção segura e
idempotente: recalcula somente agregados de 15 minutos e resumos horários de
períodos fechados ainda pendentes. Não exclui nem resume irreversivelmente as
medições originais. A aba Auditoria, exclusiva de administradores, permite
revisar as mutações administrativas e de dados relevantes; ela não registra
visualizações ou polling.

Cada zona define se sua última leitura expira após dois ou três ciclos de
coleta; três é o padrão. O limite efetivo acompanha o intervalo global de
coleta e tem piso de dez segundos.

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

A produção lê `.env.vps` (ver `.env.vps.example`) -- desde 01/09/2026, a mesma
convenção dos três projetos irmãos. Até ali este era o único dos quatro cujo
`deploy.sh` lia `.env.docker`, o MESMO nome do arquivo de desenvolvimento local;
copiar o arquivo errado para o servidor desligava `Secure` do cookie de sessão
em silêncio. Isso não depende mais só do exemplo versionado estar certo: subir
com `CONFORTO_COOKIE_SEGURO` desligado e escuta fora de host de loopback agora
recusa a inicialização (`app_factory._validar_transporte`), no mesmo espírito
de `_validar_debug` e `_validar_testing`.

## Credencial do servidor SMTP

Host, porta e usuário do SMTP continuam editáveis pela aba Configurações e
persistidos no banco -- não são segredo. A **senha não é mais gravada em lugar
nenhum da tabela `configuracoes`** (CT-03: até 01/09/2026 ela ficava lá em
texto claro, replicada em todo dump que o BackupRestore gera e cataloga). Ela
vem exclusivamente de `SMTP_PASS` (`app/models.py:_resolver_senha_smtp`), na
mesma ordem de precedência de `sharedauth.secrets.resolver_segredo`:

- `SMTP_PASS_FILE` apontando para um arquivo de segredo montado por fora deste
  Compose (não há entrada própria em `secrets:` — SMTP é opcional, e um
  segredo do Compose exige que o arquivo exista para a aplicação subir; quem
  quiser essa forma monta o arquivo e aponta a variável para ele);
- ou a variável direta `SMTP_PASS`, definida em `.env.vps` (produção) ou
  `.env.docker` (local).

**Provisionar**: defina `SMTP_PASS=<senha>` no arquivo de ambiente do processo
e suba de novo (`~/deploy.sh conforto` no VPS). Deixar em branco é a operação
normal quando não há e-mail de alerta de verdade: o envio opera em modo
simulado (o e-mail é montado e mostrado na tela, mas nada sai pela rede).

**Rotacionar**: troque o valor de `SMTP_PASS` no arquivo de ambiente do
servidor e suba de novo -- não há reinicialização adicional nem migração
envolvida, porque a senha nunca fica em disco gerido pela aplicação nem em
tabela nenhuma. A tela mostra apenas se HÁ senha configurada
(`smtpSenhaConfigurada`), nunca o valor.

Uma instalação com o defeito antigo (senha gravada antes de 01/09/2026) tem o
valor removido automaticamente pela migração
`20260902_0001_remover_smtp_senha` na próxima subida -- sem downgrade de dados
de propósito: reverter a migração não restaura a senha apagada.

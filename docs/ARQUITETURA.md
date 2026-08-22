# Arquitetura

## Componentes e fluxo

```text
navegador -> ICT -> API interna autenticada -> coletor
                \                         /
                 -------- PostgreSQL -----
```

- **ICT** (`run_ict.py`, `criar_app_ict`): única interface pública; serve HTML
  e JSON, autentica usuários, aplica perfis, mantém cadastros e configurações e
  encaminha operações ao coletor.
- **Coletor** (`run_coletor.py`, `criar_app_coletor`): serviço privado; executa
  ciclos por zona, mantém estado transitório, calcula resultados, simula
  sensores/atuadores e persiste leituras e eventos. Expõe `/health` e
  `/api/interno/*`.
- **PostgreSQL 17**: armazenamento compartilhado. `historico` contém usuários,
  configuração, zonas, equipamentos, leituras e agregados; `dados_entrada`
  contém séries geradas, cache climático e metadados de exportação.
- **Schema**: job efêmero que aplica as migrações Alembic antes de liberar os
  processos.

O SharedAuth fornece sessão, CSRF, autenticação, rate limit de login,
autorização comum, hash de senha, cabeçalhos de segurança, CSP e health checks.
Perfis e a associação entre perfis e áreas pertencem a `app/auth.py`.

## Responsabilidades de dados

O ICT grava cadastros e configurações. O coletor lê esses parâmetros e grava
leituras, estados, heartbeat e eventos. Agregados de 15 minutos e resumos
horários são derivados das leituras e podem ser recalculados. O Alembic é a
única autoridade para criar ou alterar schema.

`app/db_backend.py` adapta chamadas SQL existentes para o driver PostgreSQL;
não é um backend SQLite nem uma alternativa de persistência.

## Simulação e Modbus

`modoSimuladoZonas` é verdadeiro por padrão. Nesse modo, o simulador fornece
leituras e confirma comandos sem rede ou porta serial. O repositório contém
clientes Modbus TCP/RTU e lógica de atuação, mas esses caminhos não fazem parte
do uso atual, não foram homologados para uma instalação física e não devem ser
ativados neste projeto de pesquisa.

## Fronteiras

- o navegador não chama o coletor diretamente;
- o coletor não publica porta no host;
- autorização é aplicada no ICT antes do encaminhamento;
- o ICT não compartilha estado transitório nem importa o cliente Modbus;
- falha de um dispositivo é registrada e isolada por zona;
- a API JSON serve à interface incluída no projeto e não é uma API pública
  versionada.

Os contêineres de runtime usam usuário não-root, filesystem somente leitura,
capabilities removidas, limites de recursos, health checks e logs rotacionados.
Segredos são arquivos montados em `/run/secrets`; somente os serviços que
precisam deles recebem cada segredo.

## Instância de demonstração no VPS

Há uma instância de pesquisa e demonstração no VPS, sem equipamentos físicos.
O Nginx termina TLS em `https://conforto-mspa.duckdns.org` e encaminha ao ICT
publicado somente no loopback `127.0.0.1:5401`. O PostgreSQL também fica no
loopback, em `127.0.0.1:5402`, e o coletor continua sem porta publicada.

O código da instância é um espelho do `main`. A implantação usa o script
central `_manutencao/vps/deploy.sh`, instalado no servidor como
`~/deploy.sh`; os dados permanecem nos volumes Docker, fora do checkout. O
rollback automático do deploy restaura o código e a imagem anteriores, mas não
reverte migrações do banco.

A proteção central dos bancos local e do VPS pertence ao projeto irmão
[BackupRestore](https://github.com/MSPA-Coder/BackupRestore), não a um serviço
desta composição.

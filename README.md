# Sistema de Controle dos Índices de Conforto Térmico

Aplicação web em Python e Flask para monitorar conforto térmico na produção animal. O sistema calcula índices térmicos, acompanha zonas com sensores e atuadores, mantém o histórico no PostgreSQL e oferece visões de operação e análise com acesso controlado por perfil.

As fórmulas, faixas de classificação e espécies atendidas têm como referência a dissertação *Programa Computacional para o Cálculo de Índices de Conforto Térmico na Produção Industrial de Animais para Carne e Leite* (Mariano Sergio Pacheco de Angelo, UNIP, 2013). A implementação atual está centralizada em `app/thermal_indices.py`.

## Principais recursos

- Cálculo e classificação dos índices ITU, ITUV e IGNU.
- Monitoramento por zona com sensores, ventiladores e nebulizadores independentes.
- Modos de operação desligado, manual, automático e manutenção.
- Simulação de sensores e atuadores para uso sem hardware Modbus.
- Histórico em PostgreSQL, com séries em tempo real, agregados de 15 minutos e resumos horários. SQLite é usado somente pelos testes unitários.
- Painéis de acompanhamento, análises por zona e filtros de histórico.
- Geração de dados de entrada a partir do clima histórico disponibilizado pelo Open-Meteo.
- Alertas por e-mail, com pré-visualização quando não há SMTP configurado.
- Login obrigatório, perfis de acesso e administração de usuários.
- ICT e coletor executados como serviços independentes e supervisionados pelo Docker.

## Índices implementados

| Índice | Fórmula | Espécies |
|---|---|---|
| ITU | `0.72 * (tbs + tbu) + 40.6` | frangos, bovinos e suínos |
| ITUV | `(0.85 * tbs + 0.15 * tbu) * v ** -0.058` | frangos |
| IGNU | `0.6 * tgn + 0.36 * tpo + 41.5` | frangos, bovinos e suínos |

Cada resultado é classificado como **Conforto**, **Alerta**, **Perigo** ou **Emergência**. Os limites por espécie e índice ficam em `app/thermal_indices.py`.

## Requisitos

- Docker Desktop com Docker Compose.
- VS Code é opcional para desenvolvimento.
- Acesso à internet somente para baixar dados climáticos ainda não presentes no cache.

## Desenvolvimento com VS Code, Docker e PostgreSQL

O ambiente recomendado possui três serviços permanentes e um inicializador:

- `ict`: única interface pública, com todas as abas e autorização por perfil;
- `coletor`: malha contínua e API privada para ações Modbus;
- `postgres`: PostgreSQL 17 com volume persistente;
- `schema`: job que aplica as migrações Alembic antes de liberar os outros dois.

O PostgreSQL usa um único banco e separa as responsabilidades nos schemas
`historico` e `dados_entrada`. O esquema é versionado pelo Alembic. As portas
são publicadas somente em `127.0.0.1`.

Na primeira execução, copie o arquivo de ambiente e gere os segredos locais:

```powershell
Copy-Item .env.docker.example .env.docker
docker run --rm -v "${PWD}:/workspace" -w /workspace python:3.13-slim python scripts/configurar_segredos.py
```

Os arquivos ficam em `.secrets/`, fora do Git. Não coloque senhas nem tokens em
`.env.docker`. Em uma instalação já existente, use o procedimento de rotação
coordenada antes de substituir a senha do PostgreSQL.

Se o computador interceptar HTTPS com uma autoridade local, exporte-a antes
do build. O arquivo gerado fica fora do Git:

```powershell
.\scripts\exportar_ca_local.ps1
```

Para construir e iniciar:

```powershell
docker compose --env-file .env.docker up --build -d
docker compose --env-file .env.docker ps
docker compose --env-file .env.docker logs -f ict coletor
```

A aplicação fica em `http://127.0.0.1:5000`. No VS Code, também é possível
usar **Dev Containers: Reopen in Container**. As configurações de extensões,
testes, tarefas e depuração ficam em `.vscode/` e `.devcontainer/`.

Para parar sem apagar os dados:

```powershell
docker compose --env-file .env.docker down
```

Não use `down -v` sem intenção explícita: essa opção remove o volume do
PostgreSQL.

### Verificação do PostgreSQL

Para validar escrita, leitura, unicidade case-insensitive e rollback no banco
da pilha:

```powershell
docker compose --env-file .env.docker exec ict python -m scripts.verificar_postgres
```

### Testes no contêiner

A suíte usa PostgreSQL descartável para os testes que exercem persistência
(models, repositories, serviços e rotas que gravam dados) e não precisa de
banco algum para os testes de cálculo, validação e regras de domínio -- ver
seção "Testes" abaixo para o passo a passo completo.

```powershell
docker compose -f compose.test.yaml up -d --wait
docker run --rm --network conforto-termico-teste_default `
  -e DB_HOST=postgres_teste -e DB_PORT=5432 `
  -e DB_USER=conforto_teste -e DB_NAME=conforto_termico_teste `
  -e DB_PASSWORD_FILE=/run/secrets/postgres_password_teste `
  -e CONFORTO_TESTING=1 `
  -v "$(Resolve-Path .secrets\postgres_password_teste.txt):/run/secrets/postgres_password_teste:ro" `
  conforto-termico:local python -m unittest discover -v
docker compose -f compose.test.yaml down
```

### Backup do PostgreSQL

A ação de backup da interface usa `pg_dump` em formato custom e inclui o banco
completo — schemas `historico` e `dados_entrada`, extensões e revisão Alembic —
no volume de instância da aplicação.

O suporte a equipamentos Modbus reais já está incluído na imagem.

## Primeiro acesso

Crie o primeiro administrador antes de iniciar o uso:

```powershell
docker compose --env-file .env.docker exec ict python scripts/criar_usuario_admin.py
```

O script solicita nome, login e senha. Depois do primeiro acesso, administradores podem gerenciar as demais contas pela interface.

## Execução

No Docker, inicie sempre a pilha completa:

```powershell
docker compose --env-file .env.docker up --build -d
```

Acesse somente o ICT em `http://127.0.0.1:5000`. A porta do coletor não é
publicada no host; dentro da rede do Compose, o ICT o alcança em
`http://coletor:5000`.

## Configuração do servidor

Os valores padrão ficam em `config/servidor.json`. Variáveis de ambiente, quando definidas, têm precedência:

| Variável | Padrão | Finalidade |
|---|---:|---|
| `CONFORTO_DEBUG` | `0` | Ativa o modo de depuração do Flask (servidor de desenvolvimento, com o debugger interativo). Use somente em desenvolvimento local. |
| `CONFORTO_HOST` | `127.0.0.1` | Interface de rede usada pelo servidor. |
| `CONFORTO_PORT` | conforme o processo | Porta TCP. |
| `CONFORTO_SESSION_COOKIE_NAME` | `conforto_session` | Nome exclusivo do cookie de sessão no navegador. |
| `CONFORTO_THREADED` | `1` | Habilita atendimento concorrente. Com `CONFORTO_DEBUG=0`, controla o número de threads do `waitress` (ver abaixo). |
| `CONFORTO_MAX_CONTENT_LENGTH` | `1000000` | Limite do corpo das requisições, em bytes. |
| `CONFORTO_SECRET_KEY` | arquivo no volume gerado | Define a chave usada para assinar a sessão. |
| `CONFORTO_INTERNO_TOKEN_FILE` | `/run/secrets/internal_token` | Arquivo de segredo compartilhado entre ICT e coletor para a API interna. |
| `CONFORTO_COOKIE_SEGURO` | `0` | Use `1` quando o acesso externo estiver protegido por HTTPS. |
| `COLETOR_URL` | `http://coletor:5000` no Compose | Endereço privado usado pelo ICT. |

Com `CONFORTO_DEBUG=0` (o padrão), o servidor é servido por `waitress`. O
servidor embutido do Flask/Werkzeug só é usado com `CONFORTO_DEBUG=1`.

### Configuração de implantação e configuração operacional

`.env.docker` é somente leitura para a aplicação. Ele guarda endereços, portas
e opções não secretas definidos por quem mantém a implantação. Senha do banco e
token interno ficam em Docker secrets. Alterações exigem recriar os processos
afetados.

Parâmetros mantidos pelas abas — zonas, equipamentos, endereços Modbus,
intervalos, limites, simulação e alertas — ficam no PostgreSQL. O coletor
consulta essa configuração durante a malha, de modo que alterações autorizadas
no ICT não exigem acesso ao Docker nem reescrita de `.env`.

Ao expor o serviço fora da máquina local, mantenha `CONFORTO_DEBUG=0`,
restrinja a rede de acesso e use HTTPS adequado ao ambiente, como um proxy
reverso na frente do `waitress`.

## Perfis de acesso

Todo acesso exige autenticação. As permissões são verificadas nas rotas; ocultar uma aba é apenas parte da apresentação da interface.

| Perfil | Áreas disponíveis |
|---|---|
| Operador | Dashboard e Operação |
| Técnico | Dashboard, Operação, Histórico, Cadastro, Sistema e Dados de entrada |
| Veterinário | Dashboard, Análises, Histórico e Configurações |
| Analista | Dashboard, Análises, Histórico e Dados de entrada |
| Gestor | Dashboard, Análises e Histórico |
| Administrador | Todas as áreas e gerenciamento de usuários |

A exclusão de dados de entrada é restrita a técnicos e administradores. O sistema também impede que o último administrador ativo seja removido ou desativado.

As sessões duram até 12 horas e usam cookies `HttpOnly` e `SameSite=Lax`.
Formulários e chamadas mutáveis da interface exigem token CSRF. Ao publicar por
HTTPS, habilite `CONFORTO_COOKIE_SEGURO=1`; encerre a sessão em dispositivos
compartilhados.

## Organização da interface

- **Monitoramento:** Dashboard, Análises e Histórico.
- **Operação:** modos das zonas, ciclos manuais e comandos de equipamentos.
- **Administração:** Cadastro, Configurações e Sistema.
- **Dados:** geração, consulta, exportação e cópia de dados de entrada.

A disponibilidade de cada área depende do perfil do usuário e, quando os processos são separados, do papel da aplicação.

## Zonas e Modbus

Uma zona representa uma área de produção com espécie, índice, sensores e atuadores próprios. Cada zona pode ter de zero a vários sensores, ventiladores e nebulizadores.

Os equipamentos podem usar Modbus TCP ou RTU. A configuração inclui os parâmetros de conexão, unidade, registrador e, para sensores, campo medido, tipo de dado e fator de escala.

Em cada ciclo de uma zona, o sistema:

1. lê os sensores ativos;
2. agrupa as leituras pelo campo medido;
3. calcula a média quando há mais de um sensor para o mesmo campo;
4. desconsidera sensores sem resposta e registra as falhas;
5. deriva umidade relativa e ponto de orvalho quando possível;
6. calcula e classifica o índice;
7. atualiza o estado de resfriamento da zona;
8. envia comandos aos atuadores habilitados;
9. persiste a leitura e o estado dos equipamentos.

As zonas mantêm estados de controle independentes. A falha de um sensor não bloqueia o ciclo se os campos obrigatórios continuarem disponíveis.

### Modo simulado

`modoSimuladoZonas` vem habilitado em uma instalação nova. Nesse modo, não há comunicação com rede ou porta serial: leituras são geradas pelo simulador e comandos de atuadores retornam sucesso simulado.

Antes de desabilitar a simulação:

- confira endereços, unidades, registradores e fatores de escala;
- teste a conexão de cada equipamento;
- valide as travas global e da zona;
- execute o primeiro acionamento com supervisão local.

Falhas de comunicação Modbus são convertidas em estado de leitura ou escrita malsucedida e registradas pelo fluxo de controle, sem encerrar o servidor.

## E-mail

Configure destinatário, status mínimo e servidor SMTP pela interface. Também é possível fornecer valores SMTP pelo ambiente:

```powershell
$env:SMTP_HOST = "smtp.exemplo.com"
$env:SMTP_PORT = "587"
$env:SMTP_USER = "usuario@exemplo.com"
$env:SMTP_PASS = "senha-ou-app-password"
```

Os valores persistidos têm prioridade quando não estão vazios. Sem host SMTP, o sistema prepara a mensagem, mas não realiza o envio.

A senha SMTP nunca é devolvida pela API. A interface informa apenas se existe uma senha configurada.

## Dados de entrada

A área **Dados de entrada** gera séries para zonas ativas a partir de dados climáticos históricos do Open-Meteo, complementados por cálculos psicrométricos e simulação de atividade e carga térmica animal.

Os resultados ficam no schema PostgreSQL `dados_entrada`, separado do schema
operacional `historico`. Uma execução pode ser exportada em CSV ou copiada
uma única vez para o histórico.

Consultas climáticas são armazenadas em cache. Uma geração que precise de um período ainda não armazenado depende de acesso à internet e da disponibilidade do serviço externo.

## Persistência

Os dados da aplicação ficam no volume `postgres_data`, divididos entre os
schemas `historico` e `dados_entrada`. O volume `app_instance` armazena a
chave de sessão gerada e os dumps criados pela função de backup.

Excluir uma zona remove seus equipamentos, mas preserva as leituras históricas sem vínculo com a zona.

Faça backups periódicos do PostgreSQL ou use a função disponível na área
Sistema. Não trate o diretório de código como armazenamento persistente.

Para criar uma distribuição do código sem bancos, ambiente virtual, caches e metadados locais:

```powershell
python scripts/gerar_zip_limpo.py
```

## Dados de demonstração

Para cadastrar cinco zonas de exemplo:

```powershell
docker compose --env-file .env.docker exec ict python scripts/seed_zonas.py
```

O script não adiciona zonas quando já existem registros. Use `--forcar` apenas quando quiser inserir outro conjunto:

```powershell
docker compose --env-file .env.docker exec ict python scripts/seed_zonas.py --forcar
```

## Estrutura do projeto

```text
.
├── run_ict.py                 # única interface pública
├── run_coletor.py             # serviço privado de aquisição e controle
├── compose.yaml               # supervisão e rede dos serviços
├── config/servidor.json       # configuração versionada do servidor
├── app/
│   ├── app_factory.py         # fábricas explícitas de ICT e coletor
│   ├── auth.py                # autenticação e autorização
│   ├── thermal_indices.py     # fórmulas, limites e validações
│   ├── services.py            # estratégias do simulador de sensores
│   ├── zona_service.py        # cálculo e controle por zona
│   ├── modbus_client.py       # integração com pymodbus
│   ├── database.py            # persistência operacional
│   ├── agregacao.py           # agregados de 15 minutos e horários
│   ├── dados_entrada_*.py     # geração e persistência de dados de entrada
│   ├── coletor/               # malha e API HTTP privada
│   ├── ict/                   # análises, administração e proxy operacional
│   ├── templates/             # interface HTML
│   └── static/                # CSS, JavaScript e Chart.js
├── scripts/                   # utilitários de administração e demonstração
├── tests/                     # testes automatizados
├── docs/                      # material de referência
└── instance/                  # chave de sessão e backups no volume Docker
```

## Arquitetura

`app_factory` expõe duas composições sem modo combinado:

- `criar_app_ict()`: todas as páginas e APIs públicas, sem importar Modbus;
- `criar_app_coletor()`: health-check e API `/api/interno/*`, sem páginas,
  login ou administração de usuários.

O navegador chama somente o ICT. Para calcular manualmente, alterar o modo,
comandar um atuador ou testar conexão, o ICT primeiro valida sessão e perfil e
então encaminha a ação ao coletor usando `CONFORTO_INTERNO_TOKEN`. O coletor
não publica porta no host.

Os dois processos compartilham o PostgreSQL. O ICT grava cadastros e
configurações; o coletor lê esses parâmetros, mantém o estado transitório da
malha e grava leituras, eventos e heartbeat.

As rotas compartilhadas de leitura ficam em `app/rotas_comuns.py`. Os cálculos operacionais são sempre associados a uma zona e coordenados por `app/zona_service.py`. Em desenvolvimento, `app/modbus_simulador.py` reutiliza as estratégias de geração e resfriamento de `app/services.py` para simular sensores sem hardware Modbus.

A API é interna à interface web e não possui versionamento público. Ao alterar um contrato JSON, atualize no mesmo trabalho o backend, o JavaScript consumidor, os testes e esta documentação.

## Testes

A suíte tem dois níveis, conforme o que cada teste exercita (ver AGENTS.md,
seção "Persistência e integridade"):

- **Cálculo, validação e regras de domínio** (índices térmicos, formatação,
  simulação Modbus, e-mail, notificações) não tocam banco algum e rodam em
  menos de 1 segundo:

  ```powershell
  python -m unittest discover -v
  ```

- **Models, repositories, serviços com persistência e rotas que gravam
  dados** usam um PostgreSQL descartável (nunca o banco operacional). Suba-o
  uma vez com Docker:

  ```powershell
  "troque-por-uma-senha-qualquer-so-para-teste" | Set-Content -NoNewline .secrets\postgres_password_teste.txt
  docker compose -f compose.test.yaml up -d --wait
  ```

  e exporte as variáveis de ambiente antes de rodar a suíte (mesmo comando
  acima já cobre os dois níveis; os testes sem persistência continuam
  passando normalmente com essas variáveis definidas):

  ```powershell
  $env:DB_HOST = "localhost"; $env:DB_PORT = "5433"
  $env:DB_USER = "conforto_teste"; $env:DB_NAME = "conforto_termico_teste"
  $env:DB_PASSWORD_FILE = (Resolve-Path .secrets\postgres_password_teste.txt)
  $env:CONFORTO_TESTING = "1"
  python -m unittest discover -v
  ```

  Sem essas variáveis, os testes de persistência são pulados (`skipped`) com
  uma mensagem explicando como configurá-las -- a suíte nunca cai de volta
  para SQLite silenciosamente. Ao terminar:

  ```powershell
  docker compose -f compose.test.yaml down
  ```

Os testes de Modbus usam simulações e não exigem hardware ou conectividade.
SQLite não é uma opção de implantação: as únicas exceções que ainda o usam
testam explicitamente comportamento exclusivo do próprio caminho SQLite
(documentado em cada classe), nunca persistência genérica. Antes de integrar
uma alteração ampla, valide também a pilha PostgreSQL "de produção" (imagem,
Compose, migrações) com `scripts.verificar_postgres`.

## Manutenção

As diretrizes permanentes para alterações no código estão em `agents.md`. Em resumo:

- mantenha fórmulas e limites centralizados;
- trate segurança de atuadores e segredos como contratos;
- prefira testes de comportamento a testes de detalhes internos;
- altere ou remova testes quando o requisito correspondente mudar intencionalmente;
- documente o estado atual do produto, sem registrar etapas intermediárias de desenvolvimento.

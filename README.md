# Sistema de Controle dos Índices de Conforto Térmico

Aplicacao web local em **Python 3 + Flask** para monitoramento em tempo real
e consolidacao historica de indices de conforto termico na producao animal
(aviarios, granjas de suinos e confinamentos de bovinos de leite/corte).

> Origem cientifica: os indices, faixas de classificacao e formulas usados
> aqui vem da dissertacao de mestrado *"Programa Computacional para o
> Calculo de Indices de Conforto Termico na Producao Industrial de Animais
> para Carne e Leite"* (Mariano Sergio Pacheco de Angelo, UNIP, 2013). O
> software em si foi reconstruido do zero como aplicacao web moderna; a
> dissertacao e citada aqui apenas como referencia da metodologia, nao como
> descricao do estado atual do codigo.

A interface e em portugues do Brasil. Os identificadores internos do projeto
(arquivos, modulos, funcoes, campos JSON, ids HTML e classes CSS) usam ASCII.

## Funcionalidades

- Calcula os indices **ITU**, **ITUV** e **IGNU** conforme as formulas e
  limites centralizados em `app/thermal_indices.py`.
- Classifica cada leitura em **Conforto**, **Alerta**, **Perigo** ou
  **Emergencia**, com mensagens de orientacao e cores por faixa.
- Mantem historico em SQLite para leituras manuais, simuladas e por zona.
- Aba **Analises** com o percentual de tempo em cada status termico e a
  media/minimo/maximo do indice, por zona; clicar numa linha abre o
  historico filtrado daquela zona.
- Consolida automaticamente a leitura bruta em janelas de **15 minutos**
  (media/minimo/maximo) e em **resumos horarios** (media, status da media e
  percentual de tempo em cada status), sem precisar reprocessar o historico
  inteiro a cada consulta -- ver `agregacao.py` e a secao **Banco de
  dados**. Na aba **Historico**, o card "Tendencia do indice por resolucao"
  deixa alternar entre as 3 granularidades (tempo real / 15 min / hora) para
  a zona selecionada no filtro.
- Exibe graficos com Chart.js empacotado localmente em
  `app/static/js/vendor/chart.umd.js`.
- Possui configuracoes persistidas para especie, indice, intervalos,
  calculo de umidade/ponto de orvalho, alertas, equipamentos e SMTP.
- Envia e-mails reais por SMTP quando configurado; sem SMTP, monta o conteudo
  e opera em modo simulado.
- Controla ventiladores e nebulizadores com histerese de intensidade por
  leituras consecutivas, sem reduzir niveis de uma vez.
- Suporta zonas Modbus com sensores, ventiladores e nebulizadores
  independentes por zona.
- Inclui modo simulado para zonas, permitindo demonstrar o fluxo completo sem
  hardware Modbus real.
- Inclui uma aba independente **Dados de entrada** que baixa clima historico
  ERA5 pelo Open-Meteo, calcula grandezas psicrometricas, simula atividade e
  carga termica animal e grava tudo em `instance/dados_entrada.db`. A aba
  aparece no coletor e no dashboard (somente leitura neste ultimo), gera
  apenas para zonas ativas e permite copiar uma geracao, sem duplicidade,
  para `instance/historico.db`.
- As abas sao agrupadas por area de uso (Monitoramento / Operacao /
  Administracao / Dados) em vez de uma lista plana -- ver a secao
  **Organizacao das abas por papel de uso** abaixo.

## Organizacao das abas por papel de uso

A navegacao agrupa as abas por area de uso, nao so por papel de processo
(coletor/dashboard). A ideia e que cada grupo corresponda a uma frequencia e
um risco de uso diferentes: monitorar e constante e nao-destrutivo, operar e
diario mas pode acionar equipamento fisico, administrar e raro e mexe em
fiacao/credenciais.

| Grupo | Abas | Uso tipico |
|---|---|---|
| **Monitoramento** | Dashboard, Analises, Historico | Leitura e tendencias -- quem acompanha o processo (analista, veterinario, gestor) sem precisar agir sobre ele. |
| **Operacao** | Operacao | Acao no dia a dia: modo por zona, comandos de equipamento, ciclo manual -- quem esta no campo. |
| **Administracao** | Cadastro, Configuracoes, Sistema | Configuracao pouco frequente: cadastro de zona/equipamento com fiacao Modbus, limiar de alerta por e-mail e infraestrutura tecnica (sensores, banco, SMTP, parametros de calculo). |
| **Dados** | Dados de entrada | Geracao/consulta de series historicas para validacao e testes, usada tanto por quem opera quanto por quem analisa. |

Dentro de **Administracao**, "Cadastro" (fiacao Modbus, teste de conexao) e
"Sistema" (SMTP, banco, sensores, calculos) ficam separados de
"Configuracoes" (preferencias do app e a partir de qual status avisar por
e-mail) de proposito: a primeira e uma tarefa de instalacao/tecnica, feita
raramente e por quem cuida do hardware; a segunda e uma decisao de manejo,
que quem acompanha o bem-estar animal pode querer ajustar sem precisar
enxergar credenciais de SMTP ou fator de escala de registrador Modbus.

Esse agrupamento e so organizacao visual (Fase 1): o HTML de cada aba
continua sempre renderizado no DOM independente do `papel_app`, e nenhuma
rota mudou. A separacao de acesso por PESSOA (operador/tecnico/veterinario/
analista/gestor/administrador), com login e bloqueio real das rotas de
escrita por perfil, e tratada a parte -- ver a secao **Perfis de usuario e
autenticacao** mais abaixo.

## Perfis de usuário e autenticação

Fase 2: login é exigido para **qualquer** acesso ao sistema, inclusive a
aba Dashboard -- não existe mais uso anônimo. Cada pessoa tem sua própria
conta (nome, login, senha, perfil), guardada na tabela `usuarios` do mesmo
`instance/historico.db` que coletor e dashboard já compartilhavam desde a
Fase 1 -- por isso as contas valem para os dois processos sem nenhuma
configuração extra.

### Primeiro acesso (bootstrap)

Uma instalação nova não tem nenhum usuário cadastrado, e a tela que cadastra
gente (`/usuarios`) exige estar logado como administrador -- ou seja,
ninguém consegue entrar para criar o primeiro administrador pela própria
interface. Rode uma vez, direto no banco, para quebrar esse ciclo:

```bash
python criar_usuario_admin.py
```

Pede nome, login e senha interativamente (a senha não aparece no
terminal). Depois disso, use a tela **Gerenciar usuários** (link no topo do
app, visível só para administradores) para cadastrar o resto da equipe.

### Perfis e áreas liberadas

Cada perfil libera um subconjunto das áreas da interface (ver a seção
**Organização das abas por papel de uso**, acima). "Dashboard" é a única
área presente em todos os perfis, porque essa aba nunca tem uma ação de
escrita -- é puramente informativa.

| Perfil | Áreas liberadas |
|---|---|
| Operador | Dashboard, Operação |
| Técnico | Dashboard, Operação, Histórico, Cadastro, Sistema, Dados de entrada |
| Veterinário | Dashboard, Análises, Histórico, Configurações |
| Analista | Dashboard, Análises, Histórico, Dados de entrada |
| Gestor | Dashboard, Análises, Histórico |
| Administrador | Todas, incluindo Usuários |

Duas exceções, dentro da área "Dados de entrada": **excluir** dados
(medições ou todo o histórico) fica restrito a Técnico e Administrador,
mesmo que Analista também tenha acesso de escrita à mesma área (gerar,
salvar parâmetros, exportar, copiar para o histórico) -- excluir é
irreversível, gerar/exportar não. O mapa completo endpoint-por-endpoint
está em `app/auth.py` (`AREA_POR_ENDPOINT`,
`PERFIS_EXTRA_POR_ENDPOINT`).

Este controle é aplicado em DOIS lugares, e os dois precisam concordar, mas
só um deles é controle de acesso de verdade:

- **No template** (`templates/index.html`): um botão de aba só aparece se
  `papel_app` (Fase 0/1 -- qual processo) **e** `areas_permitidas` (Fase 2
  -- qual perfil) liberarem ao mesmo tempo. Isso é só conveniência visual.
- **Nas rotas** (`auth.registrar_autenticacao`, hooks `before_request`
  registrados em toda `criar_app`): quem realmente bloqueia uma chamada de
  API indevida, mesmo que a pessoa tente direto (curl, DevTools, etc.), não
  só clicando num botão escondido.

### Sessão e segurança

- Senhas nunca são guardadas em texto puro -- hash via `werkzeug.security`
  (scrypt nesta versão). `database.py` nunca vê a senha em si, só o hash já
  pronto (ver `auth.py`).
- A sessão dura 12h e usa cookie `HttpOnly` + `SameSite=Lax`. Isso cobre o
  caso comum de CSRF (POST vindo de outro site), mas este projeto não
  implementa proteção CSRF por token -- não substitui o hábito de clicar em
  **Sair** ao encerrar o uso num dispositivo compartilhado (ex.: tablet na
  fazenda).
- Desativar uma conta (`ativo = não` na tela de usuários) derruba qualquer
  sessão já aberta dessa conta na próxima requisição -- não precisa esperar
  o cookie expirar sozinho.
- Sempre existe pelo menos um administrador ativo: o sistema recusa
  desativar, rebaixar ou excluir o único administrador restante, e uma
  conta não consegue remover o próprio acesso de administrador enquanto
  está logada nela (mesmo que exista outro administrador) -- evita
  auto-lockout por engano.
- Login errado e login inexistente devolvem a mesma mensagem
  ("Login ou senha inválidos"), de propósito -- diferenciar os dois
  permitiria descobrir quais logins existem só tentando senhas ao acaso.

### Chave de sessão

Por padrão, a chave usada para assinar o cookie de sessão é gerada
automaticamente e guardada em `instance/secret_key.txt` (criado com
permissão `600`, já coberto pelo `.gitignore`) na primeira vez que o
sistema sobe. Para fixar uma chave própria (recomendado em produção, ou se
`instance/` for recriado com frequência), defina a variável de ambiente
antes de rodar:

```bash
export CONFORTO_SECRET_KEY="uma-string-aleatoria-bem-longa"
```

## Estrutura

```text
.
├── app.py                              # lancador (1 processo so): python app.py
├── run_coletor.py                      # lancador do processo COLETOR (fase 1)
├── run_dashboard.py                    # lancador do processo DASHBOARD (fase 1)
├── config/servidor.json                # portas/defaults por papel do servidor
├── conforto_termico/
│   ├── web.py                          # composicao "1 processo so" (fase 0); reexporta app/servicos
│   ├── app_factory.py                  # criar_app(papel_app): monta o Flask a partir dos blueprints
│   ├── rotas_comuns.py                 # rotas somente-leitura usadas pelos dois papeis (/, /api/zonas GET, ...)
│   ├── coletor/
│   │   ├── estado.py                   # instancia ZonaService e os demais servicos com estado
│   │   └── rotas.py                    # rotas que falam Modbus, calculam e gravam
│   ├── dashboard/
│   │   └── rotas.py                    # rotas de leitura (analises, painel executivo)
│   ├── thermal_indices.py              # formulas, limites e validacoes
│   ├── models.py                       # Temperatura, Resfriamento e Email
│   ├── services.py                     # fluxo manual/simulado da estacao principal
│   ├── zona_service.py                 # fluxo por zona Modbus (malha de controle)
│   ├── modbus_client.py                # adaptador pymodbus opcional
│   ├── modbus_simulador.py             # simulador de sensores/atuadores por zona
│   ├── database.py                     # SQLite: configuracoes, zonas, historico e estado dos equipamentos
│   ├── dados_entrada_db.py              # SQLite isolado das series historicas/simuladas
│   ├── gerador_dados.py                 # ERA5, interpolacao e simulacao animal
│   ├── dados_entrada_rotas.py           # API da aba Dados de entrada
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── tests/                              # unittest
├── scripts/seed_zonas.py               # cria zonas de exemplo
├── requirements.txt
└── instance/
    ├── historico.db                    # banco local criado/usado em runtime
    └── dados_entrada.db                # banco isolado criado pela nova aba
```

## Arquitetura

O sistema esta organizado em torno de dois PAPEIS (`papel_app`), pensados
para eventualmente rodar em processos -- e maquinas -- separados:

- **coletor** (`coletor/rotas.py` + `coletor/estado.py`): fala Modbus, le
  sensores, calcula o indice, aciona ventilador/nebulizador e grava tudo
  no banco (leituras, estado dos equipamentos). E aqui que fica a malha de
  controle (`zona_service.py`) -- ela precisa continuar funcionando mesmo
  que nenhum dashboard esteja de pe. O agendador de backend
  (`coletor/controle.py`) executa somente zonas em modo `automatico`, com
  lock por zona e heartbeat persistido.
- **dashboard** (`dashboard/rotas.py`): so leitura -- estatisticas e o
  Dashboard de monitoramento, historico, estatisticas e o
  "Painel executivo por zona" da aba Analises. Depende SOMENTE de
  `database.py`; nunca importa `modbus_client` nem `zona_service`.
- **comum** (`rotas_comuns.py`): pagina inicial, lista de zonas,
  navegacao pelo historico persistido e diagnostico -- rotas somente
  leitura uteis nos dois papeis.

`app_factory.criar_app(papel_app)` monta o Flask a partir desses
Blueprints. O modo combinado (`papel_app=None`, ver `web.py`/`app.py`) ainda
existe por compatibilidade e desenvolvimento local. `run_coletor.py` e
`run_dashboard.py` tambem funcionam de forma independente
(`papel_app="coletor"`/`"dashboard"`, cada um so com as rotas do seu papel).
Os dois processos compartilham o MESMO arquivo `instance/historico.db` -- o
`_conexao()` de `database.py` ja liga WAL e usa timeout de lock pensando
nesse cenario.

O estado desejado e o estado confirmado de cada equipamento sao persistidos
a cada ciclo (`database.salvar_estado_equipamentos`, tabela
`estado_equipamentos`). Uma janela curta de todas as leituras tambem e
persistida em `leituras_recentes_zona`, para que os graficos ao vivo nao
dependam da memoria do coletor. A operacao usa quatro modos por zona:
`desligado`, `manual`, `automatico` e `manutencao`; o acionamento fisico
exige tanto a trava global quanto a trava da propria zona.

O unico modulo que importa `pymodbus` diretamente e `modbus_client.py`.

## Indices implementados

| Indice | Formula | Disponivel para |
|---|---|---|
| ITU | `0.72 * (tbs + tbu) + 40.6` | frangos, bovinos, suinos |
| ITUV | `(0.85 * tbs + 0.15 * tbu) * v ** -0.058` | frangos |
| IGNU | `0.6 * tgn + 0.36 * tpo + 41.5` | frangos, bovinos, suinos |

As faixas de classificacao ficam em `LIMITES`, dentro de
`thermal_indices.py`. Os dicionarios compartilhados desse modulo sao
congelados com `MappingProxyType`; ao adicionar uma especie, indice, limite ou
campo, edite o literal antes da chamada a `_congelar`.

## Como rodar

Crie ou selecione um ambiente Python 3.10+ e instale as dependencias:

```powershell
pip install -r requirements.txt
```

Antes do primeiro acesso, crie o usuário administrador (uma vez só -- ver
"Perfis de usuário e autenticação", acima):

```powershell
python criar_usuario_admin.py
```

### Um processo so (padrao)

```powershell
python app.py
```

Acesse `http://127.0.0.1:5000` -- todas as abas (Dashboard, Operacao,
Analises, Historico, Cadastro, Configuracoes, Sistema, Dados de entrada)
ficam disponiveis nesse unico processo.

No PyCharm, abra a pasta do projeto, selecione o interpretador Python do
ambiente virtual e rode `app.py`.

### Dois processos (coletor + dashboard)

Cada um numa porta diferente, mesma maquina. As portas padrao ja estao em
`config/servidor.json` (`5000` para coletor, `5001` para dashboard):

```powershell
python run_coletor.py
```

```powershell
python run_dashboard.py
```

O coletor (`5000`) mostra Dashboard/Operacao/Cadastro/Configuracoes/Sistema/
Dados de entrada; o dashboard (`5001`) mostra Dashboard/Analises/Historico/
Dados de entrada (somente leitura). Apenas o coletor grava e comanda; o
dashboard acessa as tabelas compartilhadas em modo somente leitura. Os dois
usam o mesmo `instance/historico.db`.

## Configuracao do servidor

O arquivo `config/servidor.json` define defaults versionados por papel. Sem
variaveis de ambiente, `app.py` usa `padrao.port` (`5000`), `run_coletor.py`
usa `coletor.port` (`5000`) e `run_dashboard.py` usa `dashboard.port`
(`5001`).

As variaveis abaixo sao opcionais e sempre sobrescrevem o arquivo. Valem tanto
para `app.py` quanto para `run_coletor.py`/`run_dashboard.py`.

| Variavel | Padrao | Descricao |
|---|---:|---|
| `CONFORTO_DEBUG` | `0` | Liga o debugger do Werkzeug. Use apenas em desenvolvimento local. |
| `CONFORTO_HOST` | `127.0.0.1` | Interface de rede do Flask. |
| `CONFORTO_PORT` | `config/servidor.json` | Porta TCP. |
| `CONFORTO_THREADED` | `1` | Atende requisicoes concorrentes no servidor de desenvolvimento. |
| `CONFORTO_MAX_CONTENT_LENGTH` | `1000000` | Tamanho maximo do corpo da requisicao, em bytes. |

## Configuracoes persistidas

A rota `/api/configuracoes` salva e retorna as configuracoes do app. Todas as
chaves conhecidas passam por validacao e coercao segura em `database.py`.
Valores invalidos voltam ao padrao daquele campo.

Principais chaves:

- `especie` e `indice`: selecao global da interface, validada em conjunto.
- `coletarDados`, `modoAutomatico`, `habilitarSons`, `enviarEmails`,
  `habilitarEquipamentos`.
- `intervaloLeituraSegundos` e `intervaloGravacaoMinutos`.
- `modoPontoOrvalho`, `modoUmidadeRelativa`, `altitudeMetros`.
- `limiteUmidadeNebulizador`.
- `emailDestino`.
- `smtpHost`, `smtpPorta`, `smtpUsuario`, `smtpSenha`.
- `modoSimuladoZonas`.

`smtpSenha` e somente escrita pela API HTTP: respostas publicas sempre retornam
`smtpSenha: ""` e `smtpSenhaConfigurada: true/false`.

## E-mail

Sem SMTP configurado, o sistema apenas monta o conteudo do e-mail e informa que
o envio real nao ocorreu. Para envio real, configure o servidor SMTP pela aba
**Sistema** (host/porta/usuario/senha) e o limiar de aviso pela aba
**Configuracoes** ("Enviar a partir do status"), ou por variaveis de
ambiente:

```powershell
$env:SMTP_HOST = "smtp.seuservidor.com"
$env:SMTP_PORT = "587"
$env:SMTP_USER = "usuario@seudominio.com"
$env:SMTP_PASS = "senha-ou-app-password"
```

Quando uma chave SMTP existe tanto no banco quanto no ambiente, o valor do
banco tem prioridade se nao estiver vazio. O destinatario e validado ao salvar
a configuracao e novamente antes de montar a mensagem SMTP.

## Zonas Modbus

A aba **Cadastro** (rotulada "Zonas" internamente no codigo -- `data-aba="zonas"`,
`aba-zonas` -- por ser a mesma tela desde a Fase 0) cadastra areas de producao
com seus proprios sensores, ventiladores e nebulizadores. Cada zona define:

- nome, especie, indice e status ativo/inativo;
- 0 a N sensores;
- 0 a N ventiladores;
- 0 a N nebulizadores.

Equipamentos podem usar Modbus TCP ou RTU:

- TCP: `host`, `porta`;
- RTU: `porta_serial`, `baud_rate`;
- ambos: `unidade_id`, `tipo_registrador`, `endereco_registrador`;
- sensores: `campo_medido`, `tipo_dado`, `fator_escala`.

O calculo por zona funciona assim:

1. Le todos os sensores cadastrados na zona.
2. Agrupa leituras por `campo_medido`.
3. Usa a media das leituras quando ha mais de um sensor no mesmo campo.
4. Exclui sensores sem resposta da media e os lista em `sensores_com_falha`.
5. Deriva `ur` e `tpo` a partir de `tbs` + `tbu` quando nao houver sensor
   dedicado para esses campos.
6. Calcula o indice da zona.
7. Atualiza o estado de resfriamento daquela zona.
8. Escreve o estado nos ventiladores/nebulizadores cadastrados.
9. Grava a leitura em `leituras` com `zona_id`.

Cada zona tem uma instancia propria de `Resfriamento`, portanto intensidade e
histerese sao independentes entre zonas.

### Modo simulado de zonas

`modoSimuladoZonas` vem ligado por padrao. Nesse modo:

- leituras de sensores sao geradas por `modbus_simulador.py`;
- atuadores sempre respondem como escrita bem-sucedida;
- teste de conexao retorna sucesso;
- nenhum acesso real a rede ou porta serial e feito.

Desligue esse modo somente quando o hardware Modbus real estiver conectado e a
dependencia opcional `pymodbus` estiver instalada:

```powershell
pip install pymodbus
```

`modbus_client.py` nunca propaga excecoes: falhas de conexao, biblioteca
ausente e respostas Modbus de erro viram `None` em leitura ou `False` em
escrita/teste.

## Dados de exemplo

Para popular o banco com cinco zonas demonstrativas:

```powershell
python scripts/seed_zonas.py
```

O script e idempotente: se ja houver zonas, ele nao cria duplicatas. Para
forcar nova insercao:

```powershell
python scripts/seed_zonas.py --forcar
```

## API principal

Rotas principais:

| Metodo | Rota | Uso |
|---|---|---|
| `GET` | `/` | Interface web. |
| `POST` | `/api/calcular` | Calculo manual/simulado da estacao unica. |
| `GET` | `/api/sensor` | Leitura simulada da estacao unica. |
| `GET` | `/api/historico` | Historico persistido por especie/indice. |
| `GET` | `/api/historico-todos` | Historico persistido de todos os indices da especie. |
| `GET` | `/api/historico-leituras` | Historico paginado/filtravel (zona, especie, indice, status, periodo). |
| `GET` | `/api/historico-grafico` | Historico visual em memoria por especie/indice. |
| `GET` | `/api/historico-grafico-todos` | Historico visual de todos os indices da especie. |
| `GET` | `/api/configuracoes` | Consulta configuracoes publicas. |
| `POST` | `/api/configuracoes` | Salva configuracoes. |
| `POST` | `/api/reset` | Limpa historico da estacao unica. |
| `GET` | `/api/diagnostico` | Verifica banco e total de leituras. |
| `POST` | `/api/backup-banco` | Gera uma copia do arquivo do banco de dados. |

Rotas de zonas:

| Metodo | Rota | Uso |
|---|---|---|
| `GET` | `/api/zonas` | Lista zonas. |
| `POST` | `/api/zonas` | Cria zona. |
| `GET` | `/api/analises` | Estatisticas por zona: percentual de tempo em cada status e media/minimo/maximo do indice (aba Analises). |
| `GET` | `/api/zonas/<zona_id>` | Obtem zona. |
| `PUT` | `/api/zonas/<zona_id>` | Atualiza zona. |
| `DELETE` | `/api/zonas/<zona_id>` | Exclui zona e seus equipamentos. |
| `POST` | `/api/zonas/<zona_id>/equipamentos` | Cria equipamento. |
| `PUT` | `/api/zonas/<zona_id>/equipamentos/<equipamento_id>` | Atualiza equipamento. |
| `DELETE` | `/api/zonas/<zona_id>/equipamentos/<equipamento_id>` | Exclui equipamento. |
| `POST` | `/api/zonas/<zona_id>/equipamentos/<equipamento_id>/testar-conexao` | Testa conexao. |
| `POST` | `/api/zonas/<zona_id>/calcular` | Calcula uma zona por sensores ou entradas manuais. |
| `POST` | `/api/zonas/calcular-ativas` | Calcula todas as zonas ativas em sequencia. |
| `GET` | `/api/zonas/<zona_id>/historico` | Historico visual da zona. |
| `GET` | `/api/zonas/<zona_id>/agregados-15min` | Serie consolidada a cada 15 min (media/minimo/maximo do indice e das entradas). |
| `GET` | `/api/zonas/<zona_id>/resumo-horario` | Serie consolidada por hora (media/minimo/maximo, status da media e % de tempo em cada status). Aceita `data_inicio`/`data_fim`. |

Todas as rotas `/api/*` retornam JSON em erros conhecidos e tambem em erros
inesperados. Detalhes internos ficam no log do Flask; a resposta HTTP usa
mensagem generica.

## Banco de dados

O banco SQLite fica em `instance/historico.db`. Tabelas principais:

- `leituras`: historico de calculos, com `zona_id` nulo para fluxo de estacao
  unica e preenchido para fluxo por zona.
- `agregados_15min`: consolidacao automatica da leitura bruta a cada janela
  fechada de 15 minutos (media/minimo/maximo do indice e de cada entrada).
  Gerada por `agregacao.py`, chamada a cada ciclo do coletor automatico.
- `resumos_horarios`: consolidacao automatica por hora fechada (media,
  minimo, maximo, status classificado a partir da media horaria e
  percentual de leituras da hora em cada status). E a granularidade usada
  para reportar ITU/IGNU na literatura de conforto termico -- ver
  `docs/ANALISE_DE_DADOS.pdf`.
- `configuracoes`: chave/valor JSON sanitizado.
- `zonas`: cadastro das zonas.
- `equipamentos`: cadastro dos sensores e atuadores de cada zona.

`leituras.zona_id` usa `ON DELETE SET NULL`: excluir uma zona remove seus
equipamentos, mas preserva leituras historicas.

## Testes

Execute a suite completa:

```powershell
.\.venv\Scripts\python -m unittest discover -v
```

Se nao houver ambiente virtual:

```powershell
python -m unittest discover -v
```

Os testes cobrem formulas, validacao, persistencia, SMTP, APIs Flask,
simulacao, cliente Modbus com fakes, fluxo por zona e autenticacao/perfis
de usuario (`test_auth.py`, `test_database.py::TestUsuariosCRUD`,
`test_criar_usuario_admin.py`). Testes de Modbus nao dependem de hardware
real nem de rede disponivel.

## Manutencao

Regras de manutencao importantes:

- Mantenha formulas, limites e mapeamentos em `thermal_indices.py`.
- Nao una `CalculoIctService` e `ZonaService`; eles representam fluxos
  distintos.
- Nao importe `pymodbus` fora de `modbus_client.py`.
- Para novas configuracoes persistidas, adicione coercao em
  `_sanitizar_configuracoes`.
- Para novos campos/indices/especies, atualize testes e `scripts/seed_zonas.py`.
- Preserve campos JSON existentes, salvo quando uma mudanca de contrato for
  explicitamente desejada.

Consulte `agents.md` para as regras completas usadas por agentes de codigo.

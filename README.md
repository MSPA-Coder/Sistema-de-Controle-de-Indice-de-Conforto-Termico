# Sistema de Controle dos Indices de Conforto Termico

Aplicacao web local em **Python 3 + Flask** para monitoramento de indices de
conforto termico na producao animal, baseada na dissertacao de mestrado
*"Programa Computacional para o Calculo de Indices de Conforto Termico na
Producao Industrial de Animais para Carne e Leite"* (Mariano Sergio Pacheco de
Angelo, UNIP, 2013).

A interface e em portugues do Brasil. Os identificadores internos do projeto
(arquivos, modulos, funcoes, campos JSON, ids HTML e classes CSS) usam ASCII.

## Funcionalidades

- Calcula os indices **ITU**, **ITUV** e **IGNU** conforme as formulas e
  limites centralizados em `conforto_termico/thermal_indices.py`.
- Classifica cada leitura em **Conforto**, **Alerta**, **Perigo** ou
  **Emergencia**, com mensagens de orientacao e cores por faixa.
- Mantem historico em SQLite para leituras manuais, simuladas e por zona.
- Aba **Analises** com o percentual de tempo em cada status termico e a
  media/minimo/maximo do indice, por zona; clicar numa linha abre o
  historico filtrado daquela zona.
- Exibe graficos com Chart.js empacotado localmente em
  `conforto_termico/static/js/vendor/chart.umd.js`.
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

### Um processo so (padrao)

```powershell
python app.py
```

Acesse `http://127.0.0.1:5000` -- todas as abas (Dashboard, Operacao,
Analises, Historico, Zonas, Configuracoes) ficam disponiveis nesse unico
processo.

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

O coletor (`5000`) mostra Dashboard/Operacao/Zonas/Configuracoes; o
dashboard (`5001`) mostra Dashboard/Analises/Historico. Apenas o coletor
grava e comanda; o dashboard acessa as tabelas compartilhadas em modo
somente leitura. Os dois usam o mesmo `instance/historico.db`.

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
o envio real nao ocorreu. Para envio real, configure pela aba **Configuracoes**
ou por variaveis de ambiente:

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

A aba **Zonas** cadastra areas de producao com seus proprios sensores,
ventiladores e nebulizadores. Cada zona define:

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

Todas as rotas `/api/*` retornam JSON em erros conhecidos e tambem em erros
inesperados. Detalhes internos ficam no log do Flask; a resposta HTTP usa
mensagem generica.

## Banco de dados

O banco SQLite fica em `instance/historico.db`. Tabelas principais:

- `leituras`: historico de calculos, com `zona_id` nulo para fluxo de estacao
  unica e preenchido para fluxo por zona.
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
simulacao, cliente Modbus com fakes e fluxo por zona. Testes de Modbus nao
dependem de hardware real nem de rede disponivel.

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

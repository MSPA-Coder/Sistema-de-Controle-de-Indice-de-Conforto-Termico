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

## Estrutura

```text
.
├── app.py                              # lancador: python app.py
├── conforto_termico/
│   ├── web.py                          # Flask, rotas HTTP e composicao
│   ├── thermal_indices.py              # formulas, limites e validacoes
│   ├── models.py                       # Temperatura, Resfriamento e Email
│   ├── services.py                     # fluxo manual/simulado da estacao principal
│   ├── zona_service.py                 # fluxo por zona Modbus
│   ├── modbus_client.py                # adaptador pymodbus opcional
│   ├── modbus_simulador.py             # simulador de sensores/atuadores por zona
│   ├── database.py                     # SQLite, configuracoes, zonas e historico
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── tests/                              # unittest
├── seed_zonas.py                       # cria zonas de exemplo
├── requirements.txt
└── instance/
    └── historico.db                    # banco local criado/usado em runtime
```

## Arquitetura

O codigo separa quatro responsabilidades principais:

- `thermal_indices.py`: dominio puro. Contem formulas, especies, indices,
  campos exigidos, limites, mensagens e validacao numerica.
- `services.py`: fluxo manual/simulado de estacao unica, usado pelas APIs
  originais `/api/calcular`, `/api/sensor` e historicos por especie/indice.
- `zona_service.py`: fluxo independente por zona. Le sensores Modbus,
  calcula medias por campo, deriva `ur`/`tpo` quando possivel, calcula o
  indice e aciona atuadores daquela zona.
- `database.py`: persistencia SQLite, incluindo configuracoes sanitizadas,
  historico, zonas e equipamentos.

`web.py` contem apenas a camada HTTP e a composicao das dependencias. O unico
modulo que importa `pymodbus` diretamente e `modbus_client.py`.

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

Execute:

```powershell
python app.py
```

Acesse:

```text
http://127.0.0.1:5000
```

No PyCharm, abra a pasta do projeto, selecione o interpretador Python do
ambiente virtual e rode `app.py`.

## Configuracao do servidor

As variaveis abaixo sao opcionais. Sem configuracao, o servidor escuta apenas
em `127.0.0.1:5000` com debug desligado.

| Variavel | Padrao | Descricao |
|---|---:|---|
| `CONFORTO_DEBUG` | `0` | Liga o debugger do Werkzeug. Use apenas em desenvolvimento local. |
| `CONFORTO_HOST` | `127.0.0.1` | Interface de rede do Flask. |
| `CONFORTO_PORT` | `5000` | Porta TCP. |
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
python seed_zonas.py
```

O script e idempotente: se ja houver zonas, ele nao cria duplicatas. Para
forcar nova insercao:

```powershell
python seed_zonas.py --forcar
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
| `GET` | `/api/historico-grafico` | Historico visual em memoria por especie/indice. |
| `GET` | `/api/historico-grafico-todos` | Historico visual de todos os indices da especie. |
| `GET` | `/api/configuracoes` | Consulta configuracoes publicas. |
| `POST` | `/api/configuracoes` | Salva configuracoes. |
| `POST` | `/api/reset` | Limpa historico da estacao unica. |
| `GET` | `/api/diagnostico` | Verifica banco e total de leituras. |

Rotas de zonas:

| Metodo | Rota | Uso |
|---|---|---|
| `GET` | `/api/zonas` | Lista zonas. |
| `POST` | `/api/zonas` | Cria zona. |
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
- Para novos campos/indices/especies, atualize testes e `seed_zonas.py`.
- Preserve campos JSON existentes, salvo quando uma mudanca de contrato for
  explicitamente desejada.

Consulte `agents.md` para as regras completas usadas por agentes de codigo.

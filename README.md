# Sistema de Controle dos Índices de Conforto Térmico

Implementação em **Python 3 + Flask** do programa descrito na dissertação de
mestrado *"Programa Computacional para o Cálculo de Índices de Conforto
Térmico na Produção Industrial de Animais para Carne e Leite"*
(Mariano Sergio Pacheco de Angelo, UNIP, 2013 — orientador Prof. Dr. Oduvaldo
Vendrametto). O programa original foi feito em C#/Visual Studio 2012 (Windows
Forms); esta versão reimplementa o mesmo motor de cálculo e as mesmas
funcionalidades como uma aplicação web local.

## O que o sistema faz

- Calcula três índices de conforto térmico — **ITU**, **ITUV** e **IGNU** —
  para **frangos de corte**, **bovinos de leite** e **suínos**, exatamente
  como descrito na seção 4.3 da dissertação (ITUV só existe para avicultura).
- Classifica cada leitura em **Conforto / Alerta / Perigo / Emergência**
  segundo a Tabela 4 da dissertação, com a cor e a mensagem de orientação de
  cada faixa (reproduzidas das Figuras 16-29).
- Simula o acionamento remoto de **ventilador e nebulizador**, com
  intensidade crescente conforme a gravidade (seção 4.3). O bloco de
  equipamentos mostra 1 ícone por equipamento ligado quando a intensidade é
  "baixa", 2 ícones quando é "média" e 3 ícones quando é "máxima" — e cada
  equipamento (ventilador/nebulizador) é tratado de forma independente: se
  o estado indicar que só um dos dois está ligado, os ícones acesos
  aparecem apenas naquele.
- Monta e (opcionalmente) envia **e-mails de aviso** no mesmo formato das
  Figuras 20/22/25/28.
- Toca um **som de alerta** (Web Audio API, sem precisar de arquivo de áudio).
- Permite **simular a leitura de sensores remotos** (opção "Coletar Dados")
  e um **modo automático** que simula o monitoramento contínuo a cada 1 s.
  Quando os equipamentos remotos estão ligados, o sensor simulado deixa de
  sortear novos valores e reduz a carga térmica em 5% por ciclo até o índice
  voltar à faixa de Conforto; depois disso, retorna à geração aleatória.
- Mantém um **histórico das últimas 20 leituras** (SQLite) e o exibe em dois
  gráficos (valor do índice / variáveis de entrada) e em uma tabela.
- **Zonas** (aba dedicada): agrupam sensores, ventiladores e nebulizadores
  reais conectados via **Modbus** (TCP ou RTU/RS-485), de 0 a N equipamentos
  de cada tipo por zona. O cálculo do índice passa a ser feito por zona —
  quando há mais de um sensor para o mesmo campo, o valor usado é a
  **média** das leituras. Cada zona tem sua própria espécie/índice e seu
  próprio estado de ventilador/nebulizador, independente das demais. Ver
  "Zonas Modbus" abaixo.

## Estrutura do projeto

```
sistema_conforto_termico/
├── app.py                     # lançador compatível: python app.py
├── conforto_termico/
│   ├── web.py                 # rotas Flask (API + página)
│   ├── models.py              # classes Temperatura / Resfriamento / Email
│   │                           #   (inspiradas na Figura 14 da dissertação)
│   ├── services.py            # serviços de aplicação: histórico visual,
│   │                           #   sensor simulado e estratégia de resfriamento
│   ├── thermal_indices.py     # equações, Tabela 4 e validação de entradas
│   ├── database.py            # persistência SQLite do histórico
│   ├── templates/index.html
│   └── static/
│       ├── css/style.css
│       ├── js/app.js
│       └── js/vendor/chart.umd.js  # Chart.js empacotado localmente (sem CDN)
├── tests/
│   ├── test_app.py            # testes de API e fluxos integrados
│   ├── test_database.py       # testes da persistência e intervalo mínimo
│   ├── test_services.py       # testes da camada de serviços
│   └── test_thermal_indices.py
│                               # testes dos exemplos numéricos da dissertação
├── historico.db               # banco SQLite local, preservado na raiz
└── requirements.txt
```

## Diretrizes para agentes e manutencao

Este repositorio inclui `agents.md` com regras para futuros agentes e
mantenedores. Em resumo:

- preserve a separacao entre dominio, servicos, rotas HTTP, persistencia e UI;
- use padroes ja presentes no codigo, como Service Layer, Strategy e funcoes
  puras para formulas;
- adicione testes para alteracoes em formulas, sensores, modo automatico,
  equipamentos remotos, persistencia ou API;
- mantenha identificadores tecnicos sem acentos: nomes de arquivos, modulos,
  classes, metodos, funcoes, variaveis, campos JSON, ids HTML, classes CSS,
  abas, controles e valores internos de estado;
- use acentos apenas em textos exibidos ao usuario final, como labels,
  mensagens, e-mails e status visiveis.

## Arquitetura

- `app.py` é apenas o lançador compatível para `python app.py`.
- `conforto_termico/web.py` contém a camada HTTP: rotas, validação de status
  HTTP e montagem das respostas JSON.
- `conforto_termico/services.py` contém a camada de serviços da aplicação. O histórico visual
  dos gráficos fica separado do histórico persistido, e o sensor simulado usa
  o padrão **Strategy** para alternar entre geração aleatória e resfriamento
  progressivo quando os equipamentos estão ligados.
- `conforto_termico/database.py` concentra a persistência SQLite e expõe uma API pequena para
  salvar, consultar e limpar leituras.
- `conforto_termico/thermal_indices.py` permanece como núcleo puro de domínio: fórmulas,
  validação de entradas e classificação por faixa.

## Equações implementadas

A dissertação cita várias equações na revisão bibliográfica, mas a Tabela 3
("Algoritmos para determinação dos Índices de Conforto Térmico") define quais
delas foram **de fato codificadas no programa** — e são essas que estão
implementadas aqui, em `conforto_termico/thermal_indices.py`:

| Índice | Equação                                          | Fonte                    |
|--------|---------------------------------------------------|--------------------------|
| ITU    | `0,72 × (tbs + tbu) + 40,6`                        | Kelly & Bond, 1971 (Eq. 1) |
| ITUV   | `(0,85×Tbs + 0,15×Tbu) × V^(-0,058)`               | Tao & Xin, 2003 (Eq. 5) |
| IGNU   | `0,6×Tgn + 0,36×Tpo + 41,5`                        | Buffington et al., 1981 (Eq. 6) |

As três fórmulas foram conferidas manualmente contra os exemplos numéricos
publicados nas Tabelas 5, 6 e 7 e na seção 4.3 do Capítulo IV — por exemplo,
tbs=27, tbu=19 → ITU=73,72; Tgn=42, Tpo=8 → IGNU=69,58; tbs=22, tbu=1, V=4 →
ITUV=17,39 — e batem exatamente. Veja `tests/test_thermal_indices.py`.

## ⚠️ Duas premissas assumidas na Tabela 4

A Tabela 4 ("Valores limites de ITU, ITUV e IGNU") veio com duas células
incompletas na extração do PDF, e — vale registrar — as referências citadas
nelas (**Sales et al., 2006** para ITU em suínos, e **Ferreira, 2001** para
IGNU em suínos) também não aparecem na lista de Referências Bibliográficas da
própria dissertação. Para essas duas linhas, adotei uma leitura monotônica
razoável, seguindo o mesmo padrão das demais linhas da tabela:

- **ITU — suínos**: Conforto ≤ 61, Alerta 61–65, Perigo 65–69, Emergência > 69
- **IGNU — suínos**: Conforto ≤ 69,6, Alerta 69,6–82,6, Emergência > 82,6
  (sem faixa de "Perigo" distinta, na falta de um terceiro valor na tabela)

Todas as demais linhas (ITU para frangos e bovinos; ITUV para frangos; IGNU
para frangos e bovinos) foram conferidas com sucesso contra os exemplos
numéricos do Capítulo IV e não têm essa incerteza. Se você tiver os valores
exatos de Sales et al. (2006) e Ferreira (2001), é só ajustar o dicionário
`LIMITES` em `conforto_termico/thermal_indices.py` — o restante do sistema não precisa mudar.

## Correções desta revisão

Depois do primeiro uso, três problemas foram identificados e corrigidos:

1. **Chart.js deixou de depender de CDN externo.** A versão anterior carregava
   a biblioteca de gráficos de `cdnjs.cloudflare.com`. Em qualquer rede que
   bloqueie esse domínio (firewall corporativo, bloqueador de anúncios, rede
   de fazenda sem internet), o carregamento falhava silenciosamente e a
   biblioteca `Chart` ficava indefinida no navegador. Agora o Chart.js vem
   empacotado localmente em `conforto_termico/static/js/vendor/chart.umd.js` e é servido pelo
   próprio Flask — nenhuma dependência externa em tempo de execução.
2. **O tratamento de erros no front-end (`conforto_termico/static/js/app.js`) misturava dois
   problemas diferentes sob a mesma mensagem.** Um `try/catch` único
   envolvia tanto a chamada de rede quanto a atualização da tela (inclusive
   os gráficos); se a biblioteca de gráficos falhasse ao desenhar por
   qualquer motivo, o erro aparecia disfarçado de "Falha de comunicação com
   o servidor" — mesmo quando o cálculo tinha sido concluído e gravado
   normalmente no banco. Agora as duas coisas são tratadas separadamente:
   falha de rede mostra uma mensagem sobre o servidor; falha ao desenhar os
   gráficos mostra o valor já calculado e avisa especificamente sobre os
   gráficos, sem esconder o resultado.
3. **Vazamento de conexões SQLite em `conforto_termico/database.py`.** O código usava
   `with sqlite3.connect(...) as conn:`, que comita a transação mas **não
   fecha a conexão** (comportamento documentado do módulo `sqlite3`). Cada
   cálculo abria uma conexão que nunca era liberada. Corrigido com um
   gerenciador de contexto próprio que sempre chama `conn.close()`. Também
   foi adicionado um manipulador de erro global em `app.py` que garante que
   qualquer rota `/api/*` responda em JSON mesmo diante de uma falha
   inesperada, e uma rota `/api/diagnostico` para conferir rapidamente
   quantas leituras já foram gravadas no banco.

Essas correções foram validadas com testes de carga (50+ cálculos seguidos
sem falhas e sem crescimento de conexões abertas) e testes de erro
(entradas inválidas sempre retornam JSON com HTTP 400, nunca uma página de
erro HTML).

### Segunda rodada de correções

Mais dois problemas foram relatados e corrigidos, ambos confirmados com um
navegador real (Playwright + Chromium), não só por leitura de código:

4. **"Modo automático" não parava ao desmarcar a caixa.** A causa era o uso
   de `setInterval` disparando um ciclo assíncrono (leitura simulada +
   cálculo) a cada 1s: se um ciclo demorasse mais que 1s para terminar (rede
   lenta, redesenho dos gráficos, etc.), o próximo já disparava por cima,
   empilhando execuções sobrepostas. `clearInterval` só impede *novos*
   disparos — não cancela chamadas assíncronas que já estavam em andamento,
   então esse acúmulo continuava terminando sozinho mesmo depois de
   desmarcada a caixa. Troquei por um `setTimeout` que só agenda o próximo
   ciclo depois que o anterior terminou por completo, checando uma flag
   antes de cada etapa — agora nunca há sobreposição, e desmarcar interrompe
   em no máximo a duração de um ciclo já em andamento. Testado com um
   navegador real: 3 ciclos rodaram com a caixa marcada (a cada ~1s) e
   **zero** requisições novas nos 16s seguintes a desmarcar.
5. **A altura dos gráficos crescia a cada atualização, alongando a página.**
   Bug clássico do Chart.js: com `maintainAspectRatio:false`, o gráfico
   redimensiona o canvas para o tamanho do elemento-pai — mas se esse pai
   não tiver uma altura própria fixa (só "encolhe/estica" para caber o
   conteúdo), vira um loop: o canvas cresce, o pai cresce para acompanhar, o
   canvas cresce de novo, e por aí vai. Corrigido dando ao contêiner do
   canvas uma altura fixa (`height: 220px` + `position: relative`, exigido
   pela própria documentação do Chart.js). Testado com navegador real: a
   altura do gráfico ficou em exatos 220px em 8 recálculos seguidos.

### Terceira rodada: design patterns, segurança, performance e estabilidade

Revisão geral do backend com foco em robustez de produção, sem alterar
nenhuma fórmula, limite de espécie ou contrato JSON existente (a suíte de
testes cresceu de 41 para 75 casos, todos verdes antes e depois):

6. **Debug do Flask ligado por padrão.** `app.run(debug=True, ...)` estava
   hardcoded — o console interativo do Werkzeug pode executar código
   arbitrário a quem alcançar uma página de erro. Agora o runtime é
   configurado por um objeto `AppConfig` (`conforto_termico/web.py`), lido
   de variáveis de ambiente opcionais (`CONFORTO_DEBUG`, `CONFORTO_HOST`,
   `CONFORTO_PORT`, `CONFORTO_THREADED`, `CONFORTO_MAX_CONTENT_LENGTH`),
   **desligado por padrão**. Ver a seção "Variáveis de ambiente do
   servidor" abaixo.
7. **Erros inesperados vazavam a mensagem da exceção para o cliente.** O
   handler global de erro devolvia `str(erro)` dentro do JSON de resposta —
   um vazamento de informação clássico (pode incluir caminhos de arquivo,
   nomes de tabela, etc.). O detalhe completo continua indo para o log do
   servidor (`app.logger.exception`); o cliente agora recebe sempre a mesma
   mensagem genérica.
8. **Sem validação de `especie`/`indice` nas rotas de histórico.** Uma
   espécie desconhecida em `/api/historico`, `/api/historico-todos`,
   `/api/historico-grafico(-todos)` ou `/api/sensor` retornava
   silenciosamente uma lista vazia — indistinguível de "sem histórico
   ainda". Agora essas rotas devolvem `400` com uma mensagem clara.
9. **Configurações persistidas sem validação de tipo/faixa/formato.**
   `salvar_configuracoes` só filtrava chaves desconhecidas, mas aceitava
   qualquer tipo/valor para as conhecidas — incluindo, por exemplo, um
   `emailDestino` com quebra de linha (`\r\n`), o que poderia permitir
   injeção de cabeçalhos SMTP adicionais (`Bcc:`, etc.) se esse valor
   chegasse a ser usado para montar um e-mail malicioso. Agora
   `database._sanitizar_configuracoes` valida cada campo (booleano, número
   com faixa, enum, ou formato de e-mail) e cai para o padrão seguro
   daquele campo quando o valor recebido é inválido — nunca lança exceção.
   `models.Email.enviar` também valida o destinatário de forma
   independente, como segunda camada de defesa.
10. **Tabela `leituras` sem índice.** Toda leitura de histórico e toda
    checagem de "leitura gravada há menos de X minutos" fazia uma varredura
    completa da tabela — cada vez mais lenta com o tempo em modo
    automático, já que a tabela nunca é podada. Adicionado um índice
    composto em `(especie, indice, id)`. O banco também passou a rodar em
    modo `WAL` (melhor throughput e menor bloqueio entre leitura/escrita
    simultâneas) e com um timeout de espera por lock configurado.
11. **Dicionários de configuração compartilhada eram mutáveis em tempo de
    execução.** `LIMITES`, `INDICES_POR_ESPECIE`, `CAMPOS_POR_INDICE`, etc.
    (em `thermal_indices.py`) são estado de processo único, reutilizado em
    toda requisição HTTP — um `dict` mutável ali é uma superfície de bug
    silenciosa (uma escrita acidental corromperia o comportamento para
    todo mundo até o próximo restart, sem lançar exceção nenhuma). Agora
    são congelados recursivamente com `types.MappingProxyType`; qualquer
    tentativa de escrita levanta `TypeError` imediatamente. Isso exigiu um
    `JSONProvider` customizado no Flask (`ProvedorJSON`) para que
    `jsonify`/`| tojson` continuem sabendo serializar essas estruturas.
12. **Cabeçalhos de segurança ausentes.** Adicionado
    `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
    `Referrer-Policy: no-referrer` em toda resposta, e
    `Cache-Control: no-store` nas respostas de `/api/*` (que carregam
    estado dinâmico e nunca devem ser cacheadas).
13. **Concatenação de string em `innerHTML` no front-end.** O painel de
    status montava `"<strong>" + status + ":</strong> " + mensagem + ...`
    diretamente. Hoje `status`/`mensagem` só vêm de um conjunto fixo de
    valores no servidor, mas o padrão em si é frágil: se um desses campos
    um dia passar a refletir algo configurável pelo usuário, isso abriria
    uma injeção de HTML/script sem nenhuma mudança necessária no
    front-end. Substituído por construção de DOM real (`createElement` +
    `textContent`) em `definirMensagemOrientacao`, que nunca interpreta o
    conteúdo como marcação.

### Quarta rodada: reorganização de cards e configuração de e-mail pela interface

14. **Card "Espécie e índice" movido para a aba Configurações.** O card
    "Valores de entrada por leitura" assumiu a posição que era dele na aba
    Principal. Espécie e índice selecionados agora são mais um parâmetro
    persistido no banco (`especie`/`indice`, junto dos demais em
    `configuracoes`), com a mesma validação acoplada usada em
    `thermal_indices.INDICES_POR_ESPECIE` (ex.: se a espécie muda para
    bovinos enquanto o índice salvo era ITUV — que só existe para frangos
    — o servidor corrige sozinho para um índice válido daquela espécie).
15. **Novo card "E-mail" na aba Configurações**, reunindo o que já existia
    (habilitar envio, destinatário) com os quatro parâmetros de SMTP até
    então só configuráveis por variável de ambiente
    (`SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS` — ver "Envio de
    e-mails de verdade" abaixo). A senha é **somente-escrita**: a API
    nunca devolve o valor real de volta (`smtpSenha` sempre volta `""`,
    acompanhado de um `smtpSenhaConfigurada: bool`), e salvar qualquer
    outro campo sem reenviar a senha não a apaga — o servidor mantém a
    senha já salva. O envio de e-mail de verdade sempre busca a senha
    direto do servidor (nunca do payload enviado pelo navegador, que
    chega vazio de propósito). As variáveis de ambiente continuam
    funcionando como estavam, como alternativa a esse card.

### Quinta rodada: Zonas Modbus

16. **Nova aba "Zonas"**: cadastro de zonas (grupos de sensores/
    ventiladores/nebulizadores conectados via Modbus TCP/RTU, 0 a N de
    cada por zona) e o cálculo do índice passou a poder ser feito **por
    zona**, com **média** das leituras quando há mais de um sensor para o
    mesmo campo. Detalhes completos na seção "Zonas Modbus" acima. Resumo
    técnico:
    - Novo módulo `modbus_client.py`: abstração sobre `pymodbus` (dependência
      opcional) que nunca lança exceção — biblioteca ausente, equipamento
      sem resposta ou erro Modbus sempre viram `None`/`False`, o mesmo
      princípio já usado para SMTP.
    - Novo módulo `zona_service.py`: lê os sensores de uma zona, tira a
      média por campo, deriva ur/ponto de orvalho quando aplicável, calcula
      o índice (reaproveitando `Temperatura`/`Resfriamento` de
      `models.py`) e aciona os atuadores da zona — com uma instância de
      `Resfriamento` **por zona** (estado de acionamento independente entre
      zonas).
    - Novas tabelas `zonas` e `equipamentos`, e uma coluna `zona_id`
      (nula, `ON DELETE SET NULL`) em `leituras` — leituras antigas e o
      fluxo manual continuam com `zona_id` nulo, sem nenhuma mudança de
      comportamento.
    - Validação de zona/equipamento **rejeita** entrada inválida em vez de
      cair para um padrão seguro (diferente das demais configurações do
      app) — um endereço Modbus errado não deve ser "corrigido"
      silenciosamente.
    - Nova API REST (`/api/zonas`, `/api/zonas/<id>/equipamentos`,
      `/api/zonas/<id>/calcular`, `/api/zonas/<id>/historico`, etc.).
    - 72 novos testes automatizados cobrindo CRUD, validação, o cliente
      Modbus (com cliente falso, sem depender de hardware real) e o
      serviço de cálculo por zona (média, resiliência a falha de sensor,
      estado independente por zona).

## Variáveis de ambiente do servidor

Todas opcionais — sem nenhuma configurada, o servidor roda com os mesmos
padrões seguros de sempre (`127.0.0.1:5000`, debug desligado):

| Variável | Padrão | Efeito |
|---|---|---|
| `CONFORTO_DEBUG` | `0` (desligado) | Liga o debugger interativo do Werkzeug. **Nunca ligue isso fora da sua máquina de desenvolvimento** — permite execução de código arbitrário a quem alcançar uma página de erro. |
| `CONFORTO_HOST` | `127.0.0.1` | Interface de rede em que o Flask escuta. |
| `CONFORTO_PORT` | `5000` | Porta TCP. |
| `CONFORTO_THREADED` | `1` (ligado) | Permite o servidor de desenvolvimento atender requisições concorrentes (útil com o modo automático, que faz polling). |
| `CONFORTO_MAX_CONTENT_LENGTH` | `1000000` (~1 MB) | Tamanho máximo aceito para o corpo de uma requisição, em bytes. |

## Como rodar no PyCharm 2026

1. Abra o PyCharm → **File → Open...** → selecione a pasta
   `sistema_conforto_termico`.
2. Configure o interpretador Python do projeto (Settings/Preferences →
   Project → Python Interpreter → crie um venv com Python 3.10 ou superior,
   caso ainda não tenha um).
3. Abra o terminal integrado do PyCharm e instale as dependências:
   ```
   pip install -r requirements.txt
   ```
4. Clique com o botão direito em `app.py` → **Run 'app'** (ou use o ícone de
   Run). O PyCharm também reconhece automaticamente projetos Flask e oferece
   uma configuração de execução do tipo "Flask Server" apontando para
   `app.py`, se preferir usá-la.
5. Acesse **http://127.0.0.1:5000** no navegador.

Na primeira execução, `conforto_termico/database.py` cria automaticamente o arquivo
`historico.db` (SQLite) na pasta do projeto — não é preciso nenhuma
configuração adicional de banco de dados.

## Envio de e-mails de verdade (opcional)

Sem nenhuma configuração, a opção "Enviar e-mails de aviso" funciona em modo
**simulado**: o conteúdo do e-mail é montado e mostrado na tela (no mesmo
formato das Figuras 20/22/25/28), mas nada é enviado de fato. Para enviar
e-mails reais via SMTP, defina estas variáveis de ambiente antes de rodar
`app.py` (por exemplo, em **Run/Debug Configurations → Environment
variables** no PyCharm):

```
SMTP_HOST=smtp.seuservidor.com
SMTP_PORT=587
SMTP_USER=usuario@seudominio.com
SMTP_PASS=sua-senha-ou-senha-de-app
```

## Zonas Modbus

A aba **Zonas** permite cadastrar áreas de produção (galpões, baias, etc.)
com seus próprios sensores, ventiladores e nebulizadores conectados via
**Modbus TCP** ou **Modbus RTU** (serial, típico de redes RS-485 com um HAT
em Raspberry Pi). Cada zona pode ter de **0 a N** equipamentos de cada tipo.

> **Sobre o nome "zona":** é o termo já usado por controladores comerciais de
> clima para avicultura/pecuária (ex.: Rotem) para uma área com climatização
> própria — foi mantido por já ser familiar ao mercado.

**Como funciona o cálculo:** ao clicar em "Ler agora" (ou quando integrado a
uma rotina automática futura), o sistema lê todos os sensores Modbus da
zona. Quando há **mais de um sensor para o mesmo campo** (ex.: dois sensores
de temperatura de bulbo seco), o valor usado no cálculo é a **média** das
leituras. Um sensor que não responde é ignorado na média (e aparece como
"sensor sem resposta"), mas não impede o cálculo a menos que seja o único
sensor daquele campo. Se a zona tiver `tbs`+`tbu` mas não tiver sensor
dedicado de umidade/ponto de orvalho, esses valores são **derivados**
automaticamente (mesma fórmula psicrométrica usada no restante do sistema).
O resultado é gravado no histórico e os ventiladores/nebulizadores da zona
são acionados via Modbus conforme a gravidade — cada zona tem seu próprio
estado de acionamento, independente das demais.

**Instalação:** a integração Modbus depende da biblioteca opcional
`pymodbus`. Sem ela instalada, o resto do app funciona normalmente — só as
zonas não conseguem ler/escrever equipamentos de verdade (a interface avisa
isso ao tentar testar uma conexão). Para habilitar:

```
pip install pymodbus
```

**Parâmetros de cada equipamento:** tipo (sensor/ventilador/nebulizador),
conexão (TCP: host + porta; RTU: porta serial + baud rate), ID do
dispositivo (slave/unit id, 1–247), tipo de registrador (holding/input para
sensores; holding/coil para atuadores), endereço do registrador, e — só
para sensores — o campo medido (tbs, tbu, ur, v, tgn ou tpo) e o fator de
escala (ex.: `0.1` para um sensor que reporta a temperatura como inteiro
`x10`). Um endereço ou parâmetro de conexão inválido é **rejeitado** no
cadastro (ao contrário das demais configurações do app, que sempre caem
para um padrão seguro) — um erro de digitação num endereço Modbus não deve
ser "corrigido" silenciosamente, já que isso arriscaria ler/escrever no
registrador errado de um equipamento real.

## Rodando os testes

```
python -m unittest -v
```

Os testes reproduzem os próprios exemplos numéricos da dissertação
(mesmo espírito da seção 4.2, "Validação dos Resultados Obtidos") e cobrem
os fluxos de API, persistência e serviços de simulação.

## Simplificações em relação ao programa original

- O programa original usava **multithreading** para não travar a interface
  durante o envio de e-mails e a leitura de sensores (seção 3.4.5). Na
  versão web, isso é naturalmente resolvido pelas chamadas assíncronas
  (`fetch`) do navegador — não foi necessário replicar threads no servidor.
- A "coleta de dados de sensores remotos" é **simulada** (gera valores
  plausíveis dentro da faixa validada no Capítulo IV). Quando o resfriamento
  está ativo, a simulação reduz temperaturas/umidade em 5% por ciclo e,
  no ITUV, aumenta a velocidade do ar em 5%, até o índice voltar a
  "Conforto". Para integrar sensores de verdade, o ponto de entrada é a rota
  `/api/sensor` em `app.py` — troque a geração aleatória pela chamada ao
  driver do fabricante do sensor (seção 3.4.3 da dissertação já descreve
  essa interface).
- O histórico fica em SQLite local. O fluxo manual/simulado da aba
  Principal continua sendo um único "posto de controle", como no programa
  original (aplicação desktop de estação única) — mas a aba **Zonas**
  adiciona suporte a múltiplas estações reais (uma por zona), cada uma com
  seu próprio estado de equipamento, mantendo o fluxo original intacto.

## Ideias para evolução futura

A própria dissertação lista propostas de trabalhos futuros (seção 5.1) que
continuam válidas aqui: um banco de sugestões validado por especialistas e
compartilhado entre produtores, novos índices, uso de redes neurais na
interpretação dos índices, e transformar o sistema em um programa
especialista pró-ativo.

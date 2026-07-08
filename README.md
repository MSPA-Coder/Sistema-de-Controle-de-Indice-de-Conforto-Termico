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

## Estrutura do projeto

```
sistema_conforto_termico/
├── app.py                     # rotas Flask (API + página)
├── models.py                  # classes Temperatura / Resfriamento / Email
│                               #   (inspiradas na Figura 14 da dissertação)
├── thermal_indices.py         # equações, Tabela 4 e validação de entradas
├── database.py                # persistência SQLite do histórico
├── test_thermal_indices.py    # testes que conferem os exemplos numéricos
│                               #   publicados na própria dissertação
├── templates/index.html
├── static/css/style.css
├── static/js/app.js
├── static/js/vendor/chart.umd.js  # Chart.js empacotado localmente (sem CDN)
└── requirements.txt
```

## Equações implementadas

A dissertação cita várias equações na revisão bibliográfica, mas a Tabela 3
("Algoritmos para determinação dos Índices de Conforto Térmico") define quais
delas foram **de fato codificadas no programa** — e são essas que estão
implementadas aqui, em `thermal_indices.py`:

| Índice | Equação                                          | Fonte                    |
|--------|---------------------------------------------------|--------------------------|
| ITU    | `0,72 × (tbs + tbu) + 40,6`                        | Kelly & Bond, 1971 (Eq. 1) |
| ITUV   | `(0,85×Tbs + 0,15×Tbu) × V^(-0,058)`               | Tao & Xin, 2003 (Eq. 5) |
| IGNU   | `0,6×Tgn + 0,36×Tpo + 41,5`                        | Buffington et al., 1981 (Eq. 6) |

As três fórmulas foram conferidas manualmente contra os exemplos numéricos
publicados nas Tabelas 5, 6 e 7 e na seção 4.3 do Capítulo IV — por exemplo,
tbs=27, tbu=19 → ITU=73,72; Tgn=42, Tpo=8 → IGNU=69,58; tbs=22, tbu=1, V=4 →
ITUV=17,39 — e batem exatamente. Veja `test_thermal_indices.py`.

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
`LIMITES` em `thermal_indices.py` — o restante do sistema não precisa mudar.

## Correções desta revisão

Depois do primeiro uso, três problemas foram identificados e corrigidos:

1. **Chart.js deixou de depender de CDN externo.** A versão anterior carregava
   a biblioteca de gráficos de `cdnjs.cloudflare.com`. Em qualquer rede que
   bloqueie esse domínio (firewall corporativo, bloqueador de anúncios, rede
   de fazenda sem internet), o carregamento falhava silenciosamente e a
   biblioteca `Chart` ficava indefinida no navegador. Agora o Chart.js vem
   empacotado localmente em `static/js/vendor/chart.umd.js` e é servido pelo
   próprio Flask — nenhuma dependência externa em tempo de execução.
2. **O tratamento de erros no front-end (`static/js/app.js`) misturava dois
   problemas diferentes sob a mesma mensagem.** Um `try/catch` único
   envolvia tanto a chamada de rede quanto a atualização da tela (inclusive
   os gráficos); se a biblioteca de gráficos falhasse ao desenhar por
   qualquer motivo, o erro aparecia disfarçado de "Falha de comunicação com
   o servidor" — mesmo quando o cálculo tinha sido concluído e gravado
   normalmente no banco. Agora as duas coisas são tratadas separadamente:
   falha de rede mostra uma mensagem sobre o servidor; falha ao desenhar os
   gráficos mostra o valor já calculado e avisa especificamente sobre os
   gráficos, sem esconder o resultado.
3. **Vazamento de conexões SQLite em `database.py`.** O código usava
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

Na primeira execução, `database.py` cria automaticamente o arquivo
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

## Rodando os testes

```
python -m unittest test_thermal_indices.py -v
```

Esses testes reproduzem os próprios exemplos numéricos da dissertação
(mesmo espírito da seção 4.2, "Validação dos Resultados Obtidos").

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
- O histórico fica em SQLite local (um único "posto de controle"), como no
  programa original (aplicação desktop de estação única).

## Ideias para evolução futura

A própria dissertação lista propostas de trabalhos futuros (seção 5.1) que
continuam válidas aqui: um banco de sugestões validado por especialistas e
compartilhado entre produtores, novos índices, uso de redes neurais na
interpretação dos índices, e transformar o sistema em um programa
especialista pró-ativo.

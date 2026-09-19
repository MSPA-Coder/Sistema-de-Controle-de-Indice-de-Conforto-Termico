# Domínio, hipóteses e limites de validação

## Índices implementados

| Índice | Fórmula implementada | Entradas | Espécies configuradas | Fonte |
|---|---|---|---|---|
| ITU | `0.72 * (tbs + tbu) + 40.6` | bulbo seco e bulbo úmido | frangos, bovinos e suínos | Eq. 1 da dissertação; forma usualmente atribuída a Thom (1959), em °C, e citada lá como Kelly & Bond (1971) |
| ITUV | `(0.85 * tbs + 0.15 * tbu) * v ** -0.058` | bulbo seco, bulbo úmido e velocidade do ar | frangos | Eq. 5 da dissertação; Tao & Xin (2003) |
| IGNU | `tgn + 0.36 * tpo + 41.5` | globo negro e ponto de orvalho | frangos, bovinos e suínos | Buffington et al. (1981) — **diverge da Eq. 6 da dissertação**, ver abaixo |

As fórmulas, faixas aceitas para entradas, combinações de espécie/índice e
limites de classificação vivem em `app/termico/thermal_indices.py`. O resultado é
classificado como Conforto, Alerta, Perigo ou Emergência conforme essas tabelas.
Algumas fontes não subdividem todas as quatro faixas; nesses casos os limites
repetidos no código fazem a classificação saltar uma faixa, sem inventar um
limiar intermediário.

A referência adotada pelo software é a dissertação *Programa Computacional para
o Cálculo de Índices de Conforto Térmico na Produção Industrial de Animais para
Carne e Leite* (Mariano Sergio Pacheco de Angelo, UNIP, 2013).

## Divergência da dissertação

A Eq. 6 da dissertação traz `0,6·Tgn` no IGNU, e o software a seguiu até
15/09/2026. As transcrições do índice de Buffington et al. (1981) usam
coeficiente 1 no globo negro, e as faixas de limite da Tabela 4 foram publicadas
nessa escala; com 0,6, um globo negro de 42 °C saía classificado como Conforto.
O motivo, as fontes consultadas e o que ainda não foi conferido estão em
[`adr/009-ignu-segue-buffington.md`](adr/009-ignu-segue-buffington.md).

Duas notas menores sobre a dissertação, sem efeito em número nenhum:

- os limites do ITUV são atribuídos a "Xiao & Xin, 2003", enquanto a equação é
  de Tao & Xin (2003) — provável grafia trocada, a conferir na lista de
  referências;
- o exemplo numérico do ITUV (tbs 22 °C, tbu 1 °C, V 4 m/s) confere a
  aritmética, mas não é um ponto físico: a 22 °C o bulbo úmido não desce de
  cerca de 6,7 °C.

## Hipóteses de cálculo

- cada zona escolhe uma espécie e um índice compatível;
- entradas obrigatórias ausentes, não numéricas ou fora das faixas do código
  são rejeitadas;
- bulbo úmido acima do bulbo seco é rejeitado, porque não existe na atmosfera e
  costuma indicar sensores trocados;
- quando configurado, um campo medido tem precedência sobre o campo derivável;
- umidade relativa e ponto de orvalho podem ser derivados de temperaturas e
  altitude quando as entradas necessárias existem;
- múltiplos sensores válidos do mesmo campo são combinados pela média;
- a falha de um sensor não invalida o ciclo se ainda houver todas as entradas
  obrigatórias;
- agregados de 15 minutos e resumos horários usam somente janelas fechadas e
  são derivados das leituras brutas.
- entradas físicas incoerentes (por exemplo, `tbu > tbs`, umidade fora de
  `0..100%`, velocidade inválida para ITUV ou valores não finitos) são
  rejeitadas; o sistema não as corrige silenciosamente por *clamp*.
- cálculos manuais, ciclos de zona e séries geradas usam a mesma sequência
  canônica de validação, arredondamento e classificação.

Timestamps persistidos por código novo são ISO-8601 com offset UTC (`+00:00`).
Linhas antigas sem offset são lidas como UTC para compatibilidade. Leituras
podem receber uma identidade de amostra; a persistência combina essa identidade
com lock transacional para que retries e ciclos concorrentes não dupliquem a
mesma amostra.

Retenção é opt-in. A variável `CONFORTO_RETENCAO_LEITURAS_DIAS` permanece em
zero por padrão e nenhuma rotina de coleta apaga leituras automaticamente.
Quando uma manutenção explicitamente chama a política com dias positivos, ela
remove apenas um lote limitado de leituras brutas; zonas, configurações e
agregados são preservados. Backup e descarte deliberado continuam pertencendo
ao fluxo operacional documentado no Runbook.

Séries da área Dados de entrada combinam clima histórico obtido do Open-Meteo
com cálculos e variáveis simuladas. Elas são dados sintéticos para pesquisa,
não medições de uma instalação animal. Períodos ausentes do cache dependem de
internet e da disponibilidade do serviço externo.

## O que foi validado

A suíte automatizada confere ITU e ITUV contra os exemplos numéricos da
dissertação, o IGNU contra a forma de Buffington et al. (1981) e a classificação
de pontos de calor conhecidos, além de regras de entrada e demais contratos de
software. Ruff, testes de segurança, testes de persistência e smoke checks medem
qualidade da implementação dentro do escopo que cada teste cobre.

## O que não foi validado

O projeto não apresenta validação experimental ou acadêmica de:

- atualidade ou adequação científica dos índices e limites para um contexto
  específico;
- precisão, calibração, posição ou representatividade de sensores;
- comportamento de equipamentos físicos ou comunicação Modbus em campo;
- efeito de ventilação ou nebulização sobre animais e instalações;
- segurança, bem-estar, produtividade ou decisões de manejo;
- equivalência entre séries simuladas e observações reais.

Mensagens e estados da interface são classificações do software. Não substituem
avaliação de profissional habilitado nem constituem comando para ação física.
Mudanças nas fórmulas ou tabelas exigem fonte explícita, revisão do domínio e
exemplos numéricos automatizados.

# IGNU segue Buffington et al. (1981), e não a Eq. 6 da dissertação

Decidido pelo mantenedor em 15/09/2026, a partir do laudo dos oito
repositórios (item 2.1 do plano de ação daquele dia).

## O que mudou

`calcular_ignu`, em `app/termico/thermal_indices.py`, passou de
`0,6·Tgn + 0,36·Tpo + 41,5` para `Tgn + 0,36·Tpo + 41,5`. O coeficiente do
globo negro deixou de ser 0,6.

É a única equação em que o software se afasta da dissertação que ele
implementa (*Programa Computacional para o Cálculo de Índices de Conforto
Térmico na Produção Industrial de Animais para Carne e Leite*, Angelo, UNIP,
2013). ITU, ITUV e as tabelas de limites continuam como lá.

## Por quê

A Eq. 6 da dissertação atribui a Buffington et al. (1981) a forma com 0,6, e
o código a reproduzia fielmente, inclusive no exemplo que a suíte conferia
(Tgn 42 °C, Tpo 8 °C → 69,58). Como o valor esperado do teste vinha da mesma
fonte da equação, nenhuma verificação automática tinha como apontar a
diferença. Três evidências indicam que o 0,6 não é o da fonte:

1. **As transcrições do índice usam coeficiente 1 no globo negro.** "BGHI =
   tbg + .36tdp + 41.5", citando Buffington et al. (1981), em *A Re-Evaluation
   of the Impact of Temperature Humidity Index (THI) and Black Globe Humidity
   Index (BGHI) on Milk Production in High Producing Dairy Cows* (Western Dairy
   Management Conference, 2011). "ITGU = TGN + 0,36·Tpo + 41,5", com a mesma
   citação, na revisão integrativa *Índice de temperatura do globo negro e
   umidade (ITGU) na avaliação da tolerância de ovinos ao calor*. Nenhuma fonte
   consultada traz 0,6.
2. **As faixas usadas pelo próprio software estão nessa escala.** Os limites do
   IGNU na Tabela 4 (74/78/84 para bovinos, de Baêta; 76 para frangos, de
   Teixeira) foram publicados para o índice com coeficiente 1.
3. **Com 0,6, a classificação perdia sentido físico.**

| Tgn °C | Tpo °C | Coeficiente 1 | Bovinos | Coeficiente 0,6 | Bovinos |
|---:|---:|---:|---|---:|---|
| 30 | 20 | 78,7 | Perigo | 66,7 | Conforto |
| 35 | 22 | 84,4 | Emergência | 70,4 | Conforto |
| 42 | 8 | 86,4 | Emergência | 69,6 | Conforto |

Com Tpo de 20 °C, um lote de frangos só saía de Conforto quando o globo negro
passava de 45,5 °C.

## O que não foi feito

O artigo original (*Black Globe-Humidity Index (BGHI) as Comfort Equation for
Dairy Cows*, Trans. ASAE 24(3):711–714) **não foi lido diretamente**: o acesso é
restrito. A decisão se apoia nas transcrições acima e na coerência com as
faixas de limite.

## Consequências

- O IGNU fica 0,4·Tgn acima do valor anterior — cerca de 12 pontos com globo
  negro a 30 °C —, e zonas que saíam Conforto passam a sair Alerta, Perigo ou
  Emergência.
- Valores e status já gravados não se recalculam sozinhos. Em 15/09/2026 a
  instância do VPS tinha uma zona com IGNU e nenhuma leitura, resumo ou
  medição, então não houve o que refazer. Numa base local com séries de IGNU
  anteriores a esta mudança, a simulação precisa ser gerada de novo.
- O exemplo da Tabela 6 da dissertação (69,58) deixa de ser reproduzido, de
  propósito. A suíte registra a divergência e confere a classificação dos três
  pontos da tabela acima.
- Numa defesa ou publicação que use estes números, a diferença para a
  dissertação precisa ser dita.

## Revisitar quando

O artigo original for consultado, ou uma fonte primária mostrar outra forma.
Nesse caso, a equação e o teste mudam juntos, com a fonte citada.

# Domínio, hipóteses e limites de validação

## Índices implementados

| Índice | Fórmula implementada | Entradas | Espécies configuradas |
|---|---|---|---|
| ITU | `0.72 * (tbs + tbu) + 40.6` | bulbo seco e bulbo úmido | frangos, bovinos e suínos |
| ITUV | `(0.85 * tbs + 0.15 * tbu) * v ** -0.058` | bulbo seco, bulbo úmido e velocidade do ar | frangos |
| IGNU | `0.6 * tgn + 0.36 * tpo + 41.5` | globo negro e ponto de orvalho | frangos, bovinos e suínos |

As fórmulas, faixas aceitas para entradas, combinações de espécie/índice e
limites de classificação vivem em `app/thermal_indices.py`. O resultado é
classificado como Conforto, Alerta, Perigo ou Emergência conforme essas tabelas.
Algumas fontes não subdividem todas as quatro faixas; nesses casos os limites
repetidos no código fazem a classificação saltar uma faixa, sem inventar um
limiar intermediário.

A referência adotada pelo software é a dissertação *Programa Computacional para
o Cálculo de Índices de Conforto Térmico na Produção Industrial de Animais para
Carne e Leite* (Mariano Sergio Pacheco de Angelo, UNIP, 2013).

## Hipóteses de cálculo

- cada zona escolhe uma espécie e um índice compatível;
- entradas obrigatórias ausentes, não numéricas ou fora das faixas do código
  são rejeitadas;
- quando configurado, um campo medido tem precedência sobre o campo derivável;
- umidade relativa e ponto de orvalho podem ser derivados de temperaturas e
  altitude quando as entradas necessárias existem;
- múltiplos sensores válidos do mesmo campo são combinados pela média;
- a falha de um sensor não invalida o ciclo se ainda houver todas as entradas
  obrigatórias;
- agregados de 15 minutos e resumos horários usam somente janelas fechadas e
  são derivados das leituras brutas.

Séries da área Dados de entrada combinam clima histórico obtido do Open-Meteo
com cálculos e variáveis simuladas. Elas são dados sintéticos para pesquisa,
não medições de uma instalação animal. Períodos ausentes do cache dependem de
internet e da disponibilidade do serviço externo.

## O que foi validado

A suíte automatizada pode conferir fórmulas contra exemplos numéricos da fonte,
regras de entrada e demais contratos de software. Ruff, testes de segurança,
testes de persistência e smoke checks medem qualidade da implementação dentro
do escopo que cada teste cobre.

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

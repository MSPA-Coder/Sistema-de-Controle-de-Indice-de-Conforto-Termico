# Instantes em `timestamptz`, não em texto

Estado: vigente. Substitui a decisão de 24/09/2026 de manter as datas em
`TEXT` (que não estava registrada em ADR).

Decidido pelo mantenedor em 11/11/2026, enquanto a série de leituras ainda
estava vazia em produção (achados SQL-L1, SQL-L10 e SQL-D1 da auditoria de
10/11/2026).

## Contexto

As colunas de data e hora eram `TEXT`, em três formatos que conviviam nas mesmas
tabelas: hora local sem offset (`datetime.now()` do contêiner), UTC sem offset
(janelas e horas agregadas) e UTC com `+00:00`. As consultas convertiam com
`::timestamp`, que descarta o offset e impede o uso de índice; trocar o `TZ`
do contêiner deslocaria heartbeat, "leitura atual" e janelas sem nenhum erro.

## Decisão

- As 36 colunas de instante são `timestamptz` e os dois dias do calendário de
  `execucoes` (`data_inicio`, `data_fim`) são `date`. A revisão
  `20261111_instantes_com_fuso` converte, distinguindo os formatos pelo próprio
  texto (offset presente vale como está; sem offset, vale o fuso que o código
  gravava na coluna) e recusando texto inválido.
- Há uma só fonte de "agora" em `app/models.py` (`agora_utc`, `agora_local`,
  `hoje_local`); um teste reprova `datetime.now()` e `date.today()` em outro
  lugar de `app/`.
- A sessão com o banco fala UTC. O que sai do banco para as APIs é UTC com
  `+00:00`, exceto o que sempre foi hora local sem offset (cadastro, estado do
  coletor, controle, eventos de operação), que volta a esse formato por
  `como_local_ingenuo`. O CSV de medições mantém o formato de `timestamp_utc`
  e `timestamp_local` de antes.

## Consequências

- Janelas e horas usam `date_bin`/`date_trunc` direto sobre a coluna.
- O deploy migra o banco (a revisão reescreve as tabelas); começa por dump novo.
- Pendência conhecida, não alterada: o filtro `data_hora_regional` lê o texto sem
  offset como UTC, e `ultimo_login_em` chega a ele em hora local sem offset (como
  sempre chegou), então a tela de usuários mostra o último acesso 3 h antes.

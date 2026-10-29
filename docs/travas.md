# Travas

Inventário das travas do repositório e de **qual teste ou qual outra garantia** responde por cada uma. A regra
está em `docs/TESTES.md` (T7 e T11): trava de banco em fluxo de dinheiro, posição ou acesso nasce com teste de
disputa que falha quando ela é retirada, ou com uma linha aqui dizendo qual garantia a cobre.

Medido em 29/10/2026 retirando cada trava numa cópia do commit e rodando os arquivos de disputa 3 vezes
(receita em T11). "Detectada" quer dizer que o teste falhou em todas as repetições sem a trava.

Os testes de `tests/test_travas_postgres.py` seguem um padrão: uma "primeira operação" muda o estado e fica aberta
(sem confirmar); a operação testada precisa esperar por ela e então enxergar o estado confirmado. A primeira só
libera quando a segunda já esperou ou terminou, então o resultado não depende de sorte de tempo.

## Travas de banco (PostgreSQL)

| Trava | Protege | Cobertura |
|---|---|---|
| `database/usuarios.py` `_bloquear_administradores` (advisory) | nunca ficar sem administrador | `test_rebaixar_o_ultimo_administrador_espera_e_e_recusado` e `test_excluir_o_ultimo_administrador_espera_e_e_recusado` (detectada) |
| `database/configuracoes.py` `conforto:configuracoes` (advisory) | gravação parcial não apaga o que outra gravação acabou de salvar | `test_salvar_configuracoes_espera_a_outra_gravacao_e_nao_perde_o_que_ela_gravou` (detectada) |
| `database/leituras.py` `conforto:leitura:<zona>:<índice>` (advisory) | duas publicações dentro do intervalo mínimo gravam uma leitura só | `test_salvar_leitura_dentro_do_intervalo_espera_a_outra_e_e_recusada` (detectada) |
| `database/leituras.py` `conforto:agregacao:<zona>:<índice>` (advisory, janela de 15 min e resumo horário) | agregar sobre as amostras já publicadas | `test_agregar_janela_espera_a_publicacao_e_inclui_a_leitura_dela` e `test_consolidar_hora_espera_a_publicacao_e_inclui_a_leitura_dela` (detectadas) |
| `dados_entrada/db.py` `conforto:publicacao:<execução>` (advisory) | uma geração é copiada ao histórico uma única vez | `test_geracao_concorrencia_postgres.py::test_duas_publicacoes_simultaneas_preservam_exatamente_uma_copia` (detectada) |
| `dados_entrada/db.py` `conforto:agregacao:...` na publicação (advisory) | publicar e consolidar a mesma zona não se atravessam | `test_geracao_integridade_postgres.py::test_publicacao_aguarda_consolidacao_da_mesma_zona` (detectada) |
| `dados_entrada/db.py` `recuperar_execucoes_expiradas` (`FOR UPDATE`) | não descartar a geração que acabou de renovar o lease | `test_geracao_concorrencia_postgres.py::test_recuperacao_aguarda_renovacao_ou_conclusao_em_curso_sem_apagar_amostras` (detectada) |
| `database/equipamentos.py` `atualizar_equipamento` (`FOR UPDATE`, com e sem zona) | atualizar equipamento que outra transação excluiu devolve "não encontrado" | `test_atualizar_equipamento_espera_a_exclusao_em_andamento_e_devolve_nao_encontrado[False/True]` (detectada) |
| `nucleo/notificacoes.py` `_reivindicar_outbox` (`FOR UPDATE SKIP LOCKED`) | duas rotinas não reivindicam o mesmo e-mail | `test_reivindicar_a_fila_pula_o_item_que_outra_transacao_ja_segura` (detectada) |

## Travas em memória (`threading.Lock`/`RLock`)

Protegem estado dentro de **um** processo e não aparecem no banco. Retiradas uma a uma, nenhum teste falha
(0 de 22), e um teste que dependa de corrida entre threads do Python não é determinístico. Não há teste para elas.

| Trava | Protege |
|---|---|
| `coletor/controle.py` trava por zona (`_executar_exclusivo`) | um ciclo ou comando por zona por vez; o segundo recebe `ZonaOcupadaError` |
| `termico/zona_service.py` (4) | resfriadores e histórico do gráfico por zona |
| `nucleo/circuit_breaker.py` (2) | contagem de falhas e tentativas em voo do disjuntor |
| `nucleo/cache.py` (4) | cache em memória |
| `seguranca/limites.py` | contagem do limitador de consultas custosas |
| `modbus/estrategias.py` (3) e `modbus/modbus_simulador.py` (7) | estado do simulador e das estratégias de cálculo |

**Pendência declarada:** estas travas valem enquanto houver **uma instância** do coletor/servidor. O desenho atual
tem uma, mas nada no código ou nos testes impede subir duas; se isso mudar, o estado deixa de ser protegido por
elas e o limitador e o disjuntor passam a contar por instância. O risco é de leitura e de limite de consulta, não
de dinheiro nem de acesso persistido. Reavaliar quando houver mais de uma instância.

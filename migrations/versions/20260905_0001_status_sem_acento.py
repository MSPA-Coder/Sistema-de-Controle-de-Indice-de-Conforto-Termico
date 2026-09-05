"""Troca o token de status "Emergência" pelo ASCII "Emergencia".

O nível térmico é um token de máquina: `classificar_status` o devolve, ele
fica gravado em texto e o código o compara como literal (`status in
("Perigo", "Emergencia")`, chaves de dicionário de percentuais, filtro do
histórico via `WHERE status = ?`). Só um dos quatro níveis tinha acento, e
essa era a única grafia acentuada em rotina/identificador/valor persistido de
todo o repositório. O acento passou a viver apenas no rótulo de exibição
(`thermal_indices.rotulo_do_status`), e o código canônico é sempre ASCII.

Sem esta migração, as linhas já gravadas com "Emergência" deixariam de casar
com o token novo: o filtro de histórico por Emergência voltaria vazio, o
"minutos em emergência hoje" pararia de contar e o percentual por status
ficaria zerado para esse nível.

Colunas afetadas (todo texto de nível térmico persistido):
- historico.leituras.status
- historico.leituras_recentes_zona.status
- historico.resumos_horarios.status_da_media
- dados_entrada.medicoes.status_termico  (fonte de historico.leituras.status
  quando uma execução de dados de entrada é exportada)
"""

from alembic import op

revision = "20260905_0001_status_sem_acento"
down_revision = "20260902_0001_remover_smtp_senha"
branch_labels = None
depends_on = None

_COLUNAS = (
    ("historico.leituras", "status"),
    ("historico.leituras_recentes_zona", "status"),
    ("historico.resumos_horarios", "status_da_media"),
    ("dados_entrada.medicoes", "status_termico"),
)


def _trocar(de: str, para: str) -> None:
    for tabela, coluna in _COLUNAS:
        op.execute(
            f"UPDATE {tabela} SET {coluna} = '{para}' WHERE {coluna} = '{de}'"
        )


def upgrade() -> None:
    _trocar("Emergência", "Emergencia")


def downgrade() -> None:
    # Reversível: a coluna volta a guardar a grafia acentuada. Só faz sentido
    # junto com a reversão do código que espera o token ASCII.
    _trocar("Emergencia", "Emergência")

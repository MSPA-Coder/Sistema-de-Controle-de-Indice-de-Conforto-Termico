"""CHECK nos campos de domínio fechado que só o Python guardava (SQL-L3).

Os indicadores 0/1 (`ativo`, `ativa`, `sucesso`, `trocar_senha`,
`acionamento_habilitado` e os estados de ventilador e nebulizador), o `perfil`,
o `modo` de operação da zona e o `modo_conexao` do equipamento eram texto ou
inteiro livre: SQL à mão ou um script futuro gravando `ativo = 2` ou
`perfil = 'admin'` passava, e a regra do último administrador (`ativo = 1`)
deixava de enxergar a linha. Ficam de fora `especie` e `indice` (a fonte única é
`thermal_indices.py` e um índice novo não deve exigir migração).

Os valores são os de hoje (`PERFIS_VALIDOS`, `MODOS_OPERACAO`, `MODOS_CONEXAO`),
copiados aqui de propósito: uma revisão não importa o código da aplicação. Um
perfil ou modo novo traz a sua própria revisão.

Idempotente: o que já existe não é recriado. Se alguma linha violar a regra, a
revisão para sem alterar nada (a transação é a da migração).
"""

from alembic import op

revision = "20261112_checks_de_dominio"
down_revision = "20261111_instantes_restantes"
branch_labels = None
depends_on = None

_BOOLEANOS = (
    ("historico.usuarios", "ativo"),
    ("historico.usuarios", "trocar_senha"),
    ("historico.zonas", "ativa"),
    ("historico.controle_zonas", "acionamento_habilitado"),
    ("historico.estado_equipamentos", "ventilador_ligado"),
    ("historico.estado_equipamentos", "nebulizador_ligado"),
    ("historico.estado_equipamentos", "ventilador_desejado"),
    ("historico.estado_equipamentos", "nebulizador_desejado"),
    ("historico.estado_equipamentos", "ventilador_confirmado"),
    ("historico.estado_equipamentos", "nebulizador_confirmado"),
    ("historico.auditoria_eventos", "sucesso"),
)

_PERFIS = ("operador", "tecnico", "veterinario", "analista", "gestor", "administrador")
_MODOS = ("desligado", "manual", "automatico", "manutencao")


def _lista(valores: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in valores)


def _regras() -> list[tuple[str, str, str]]:
    regras = [
        (tabela, f"ck_{tabela.split('.')[1]}_{coluna}_0_1", f"{coluna} IN (0, 1)")
        for tabela, coluna in _BOOLEANOS
    ]
    regras += [
        ("historico.usuarios", "ck_usuarios_perfil", f"perfil IN ({_lista(_PERFIS)})"),
        ("historico.controle_zonas", "ck_controle_zonas_modo", f"modo IN ({_lista(_MODOS)})"),
        ("historico.equipamentos", "ck_equipamentos_modo_conexao", "modo_conexao IN ('tcp', 'rtu')"),
    ]
    return regras


def upgrade() -> None:
    for tabela, nome, expressao in _regras():
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = '{nome}' AND conrelid = '{tabela}'::regclass
                ) THEN
                    ALTER TABLE {tabela} ADD CONSTRAINT {nome} CHECK ({expressao}) NOT VALID;
                END IF;
            END
            $$
        """)
        op.execute(f"ALTER TABLE {tabela} VALIDATE CONSTRAINT {nome}")


def downgrade() -> None:
    for tabela, nome, _ in _regras():
        op.execute(f"ALTER TABLE {tabela} DROP CONSTRAINT IF EXISTS {nome}")

"""Persistência e validação dos equipamentos Modbus por zona."""

from __future__ import annotations

import datetime
import json

from .. import thermal_indices as ti
from .comum import conexao
from .zonas import (
    ZonaInvalidaError,
    ZonaNaoEncontradaError,
    _validar_inteiro,
    _validar_numero,
)

TIPOS_EQUIPAMENTO = ("sensor", "ventilador", "nebulizador")
MODOS_CONEXAO = ("tcp", "rtu")
TIPOS_DADO = ("int16", "uint16", "float32")
CAMPOS_MEDIVEIS = tuple(ti.CAMPO_METADADOS.keys())


def salvar_estado_equipamentos(
    zona_id: int,
    ventilador_ligado: bool,
    nebulizador_ligado: bool,
    intensidade: str | None,
    ventilador_desejado: bool,
    nebulizador_desejado: bool,
    ventilador_confirmado: bool | None,
    nebulizador_confirmado: bool | None,
    falhas: list[str],
    qualidade: str,
) -> None:
    """Persiste estado desejado, confirmado e qualidade do último ciclo."""

    def _bool_sql(valor):
        return None if valor is None else int(bool(valor))

    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute(
            """
            INSERT INTO estado_equipamentos
                (zona_id, ventilador_ligado, nebulizador_ligado, intensidade, atualizado_em,
                 ventilador_desejado, nebulizador_desejado,
                 ventilador_confirmado, nebulizador_confirmado,
                 falhas, qualidade, ultimo_ciclo_em)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(zona_id) DO UPDATE SET
                ventilador_ligado = excluded.ventilador_ligado,
                nebulizador_ligado = excluded.nebulizador_ligado,
                intensidade = excluded.intensidade,
                atualizado_em = excluded.atualizado_em,
                ventilador_desejado = excluded.ventilador_desejado,
                nebulizador_desejado = excluded.nebulizador_desejado,
                ventilador_confirmado = excluded.ventilador_confirmado,
                nebulizador_confirmado = excluded.nebulizador_confirmado,
                falhas = excluded.falhas,
                qualidade = excluded.qualidade,
                ultimo_ciclo_em = excluded.ultimo_ciclo_em
            """,
            (
                zona_id,
                int(bool(ventilador_confirmado)) if ventilador_confirmado is not None else 0,
                int(bool(nebulizador_confirmado)) if nebulizador_confirmado is not None else 0,
                intensidade,
                agora,
                _bool_sql(ventilador_desejado),
                _bool_sql(nebulizador_desejado),
                _bool_sql(ventilador_confirmado),
                _bool_sql(nebulizador_confirmado),
                json.dumps(falhas or []),
                qualidade,
                agora,
            ),
        )


def salvar_comando_manual_atuador(
    zona_id: int,
    tipo: str,
    desejado: bool,
    confirmado: bool | None,
    falhas: list[str] | None = None,
) -> None:
    """Atualiza apenas o atuador comandado, preservando o outro grupo."""
    if tipo not in ("ventilador", "nebulizador"):
        raise ValueError("Tipo de atuador invalido.")
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    coluna_desejada = f"{tipo}_desejado"
    coluna_confirmada = f"{tipo}_confirmado"
    coluna_legada = f"{tipo}_ligado"
    qualidade = "boa" if not falhas else "degradada"

    with conexao() as conn:
        conn.execute(
            """
            INSERT INTO estado_equipamentos
                (zona_id, ventilador_ligado, nebulizador_ligado, intensidade,
                 atualizado_em, ventilador_desejado, nebulizador_desejado,
                 ventilador_confirmado, nebulizador_confirmado, falhas,
                 qualidade, ultimo_ciclo_em)
            VALUES (?, 0, 0, 'manual', ?, 0, 0, NULL, NULL, ?, ?, ?)
            ON CONFLICT(zona_id) DO NOTHING
            """,
            (zona_id, agora, json.dumps(falhas or []), qualidade, agora),
        )
        conn.execute(
            f"""
            UPDATE estado_equipamentos
            SET {coluna_desejada} = ?,
                {coluna_confirmada} = ?,
                {coluna_legada} = ?,
                intensidade = 'manual',
                falhas = ?, qualidade = ?,
                atualizado_em = ?, ultimo_ciclo_em = ?
            WHERE zona_id = ?
            """,
            (
                int(desejado),
                None if confirmado is None else int(confirmado),
                int(bool(confirmado)) if confirmado is not None else 0,
                json.dumps(falhas or []),
                qualidade,
                agora,
                agora,
                zona_id,
            ),
        )


def registrar_falha_operacional_zona(zona_id: int, mensagem: str) -> None:
    """Marca falha do ciclo sem inventar um novo estado dos equipamentos."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute(
            """
            INSERT INTO estado_equipamentos
                (zona_id, ventilador_ligado, nebulizador_ligado, intensidade,
                 atualizado_em, falhas, qualidade, ultimo_ciclo_em)
            VALUES (?, 0, 0, NULL, ?, ?, 'falha', ?)
            ON CONFLICT(zona_id) DO UPDATE SET
                falhas = excluded.falhas,
                qualidade = excluded.qualidade,
                atualizado_em = excluded.atualizado_em,
                ultimo_ciclo_em = excluded.ultimo_ciclo_em
            """,
            (zona_id, agora, json.dumps([mensagem]), agora),
        )


def validar_equipamento(dados: dict) -> dict:
    tipo = dados.get("tipo")
    if tipo not in TIPOS_EQUIPAMENTO:
        raise ZonaInvalidaError(
            f"Tipo de equipamento inválido: {tipo!r} (esperado um de {TIPOS_EQUIPAMENTO})."
        )

    nome = str(dados.get("nome", "")).strip()
    if not nome:
        raise ZonaInvalidaError("Informe um nome para o equipamento.")

    modo_conexao = dados.get("modo_conexao")
    if modo_conexao not in MODOS_CONEXAO:
        raise ZonaInvalidaError(
            f"Modo de conexão inválido: {modo_conexao!r} (esperado 'tcp' ou 'rtu')."
        )

    host = porta = porta_serial = baud_rate = None
    if modo_conexao == "tcp":
        host = str(dados.get("host", "")).strip()
        if not host:
            raise ZonaInvalidaError("Informe o host/IP para conexão Modbus TCP.")
        porta = _validar_inteiro(dados.get("porta", 502), "porta", 1, 65535)
    else:
        porta_serial = str(dados.get("porta_serial", "")).strip()
        if not porta_serial:
            raise ZonaInvalidaError(
                "Informe a porta serial (ex.: /dev/ttyUSB0 ou COM3) para conexão Modbus RTU."
            )
        baud_rate = _validar_inteiro(dados.get("baud_rate", 9600), "baud_rate", 300, 921600)

    unidade_id = _validar_inteiro(dados.get("unidade_id", 1), "unidade_id", 1, 247)
    registradores_validos = ("holding", "input") if tipo == "sensor" else ("holding", "coil")
    tipo_registrador = dados.get("tipo_registrador")
    if tipo_registrador not in registradores_validos:
        raise ZonaInvalidaError(
            f"Tipo de registrador inválido para {tipo}: {tipo_registrador!r} "
            f"(esperado um de {registradores_validos})."
        )

    endereco_registrador = _validar_inteiro(
        dados.get("endereco_registrador"), "endereco_registrador", 0, 65535
    )
    tipo_dado = dados.get("tipo_dado", "int16")
    if tipo_dado not in TIPOS_DADO:
        raise ZonaInvalidaError(
            f"Tipo de dado inválido: {tipo_dado!r} (esperado um de {TIPOS_DADO})."
        )

    fator_escala = _validar_numero(dados.get("fator_escala", 1.0), "fator_escala")
    if fator_escala == 0:
        raise ZonaInvalidaError("O fator de escala não pode ser zero.")

    campo_medido = dados.get("campo_medido")
    if tipo == "sensor":
        if campo_medido not in CAMPOS_MEDIVEIS:
            raise ZonaInvalidaError(
                f"Campo medido inválido para sensor: {campo_medido!r} "
                f"(esperado um de {CAMPOS_MEDIVEIS})."
            )
    else:
        campo_medido = None

    return {
        "tipo": tipo,
        "nome": nome[:255],
        "modo_conexao": modo_conexao,
        "host": host,
        "porta": porta,
        "porta_serial": porta_serial,
        "baud_rate": baud_rate,
        "unidade_id": unidade_id,
        "tipo_registrador": tipo_registrador,
        "endereco_registrador": endereco_registrador,
        "tipo_dado": tipo_dado,
        "fator_escala": fator_escala,
        "campo_medido": campo_medido,
    }


def criar_equipamento(zona_id: int, dados: dict) -> dict:
    """Valida e insere equipamento com a zona na mesma transação."""
    agora = datetime.datetime.now().replace(microsecond=0).isoformat(timespec="seconds")
    with conexao() as conn:
        zona_existe = conn.execute("SELECT 1 FROM zonas WHERE id = ?", (zona_id,)).fetchone()
        if zona_existe is None:
            raise ZonaNaoEncontradaError(f"Zona {zona_id} não encontrada.")
        validado = validar_equipamento(dados)
        cursor = conn.execute(
            """
            INSERT INTO equipamentos (
                zona_id, tipo, nome, modo_conexao, host, porta, porta_serial, baud_rate,
                unidade_id, tipo_registrador, endereco_registrador, tipo_dado, fator_escala,
                campo_medido, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                zona_id,
                validado["tipo"],
                validado["nome"],
                validado["modo_conexao"],
                validado["host"],
                validado["porta"],
                validado["porta_serial"],
                validado["baud_rate"],
                validado["unidade_id"],
                validado["tipo_registrador"],
                validado["endereco_registrador"],
                validado["tipo_dado"],
                validado["fator_escala"],
                validado["campo_medido"],
                agora,
            ),
        )
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return dict(linha)


def obter_equipamento(equipamento_id: int) -> dict | None:
    with conexao(escrita=False) as conn:
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
    return dict(linha) if linha else None


def atualizar_equipamento(equipamento_id: int, dados: dict) -> dict | None:
    validado = validar_equipamento(dados)
    with conexao() as conn:
        existe = conn.execute(
            "SELECT 1 FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
        if existe is None:
            return None
        conn.execute(
            """
            UPDATE equipamentos SET
                tipo = ?, nome = ?, modo_conexao = ?, host = ?, porta = ?, porta_serial = ?,
                baud_rate = ?, unidade_id = ?, tipo_registrador = ?, endereco_registrador = ?,
                tipo_dado = ?, fator_escala = ?, campo_medido = ?
            WHERE id = ?
            """,
            (
                validado["tipo"],
                validado["nome"],
                validado["modo_conexao"],
                validado["host"],
                validado["porta"],
                validado["porta_serial"],
                validado["baud_rate"],
                validado["unidade_id"],
                validado["tipo_registrador"],
                validado["endereco_registrador"],
                validado["tipo_dado"],
                validado["fator_escala"],
                validado["campo_medido"],
                equipamento_id,
            ),
        )
        linha = conn.execute(
            "SELECT * FROM equipamentos WHERE id = ?", (equipamento_id,)
        ).fetchone()
    return dict(linha)


def excluir_equipamento(equipamento_id: int) -> bool:
    with conexao() as conn:
        cursor = conn.execute("DELETE FROM equipamentos WHERE id = ?", (equipamento_id,))
    return bool(cursor.rowcount > 0)

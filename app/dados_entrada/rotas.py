"""Rotas de consulta e operacao da aba de dados de entrada."""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from .. import database as db
from ..app_factory import MENSAGEM_ERRO_INTERNO, confirmacao_de_exclusao_valida
from . import db as dados_db
from .cidades import referencias_publicas

# Consultas da aba Dados de entrada.
dados_entrada_leitura_bp = Blueprint("dados_entrada_leitura", __name__)
# Mutações pertencem ao ICT; o coletor não gera dados climáticos.
dados_entrada_bp = Blueprint("dados_entrada", __name__)


@dados_entrada_leitura_bp.route("/api/dados-entrada/configuracoes", methods=["GET"])
def obter_configuracoes():
    # `listar_configuracoes` e leitura pura. Aqui estava `sincronizar_zonas`,
    # que faz INSERT/UPDATE -- um GET que escreve. Ver a docstring de
    # `listar_configuracoes` para o porquê da troca e para onde a
    # materialização foi.
    return jsonify(dados_db.listar_configuracoes(db.listar_zonas(apenas_ativas=True)))


@dados_entrada_leitura_bp.route("/api/dados-entrada/referencias", methods=["GET"])
def obter_referencias():
    return jsonify(referencias_publicas())


@dados_entrada_bp.route("/api/dados-entrada/configuracoes", methods=["PUT"])
def salvar_configuracoes():
    dados = request.get_json(force=True, silent=True) or {}
    zonas = dados.get("zonas")
    if not isinstance(zonas, list) or not all(isinstance(zona, dict) for zona in zonas):
        return jsonify({"erro": "zonas deve ser uma lista de configurações."}), 400
    try:
        configuracoes = dados_db.salvar_configuracoes_zonas(
            zonas, db.listar_zonas(apenas_ativas=True)
        )
    except dados_db.ConfiguracaoDadosEntradaError:
        return jsonify({"erro": "As configurações de dados de entrada são inválidas."}), 400
    return jsonify(configuracoes)


@dados_entrada_bp.route("/api/dados-entrada/gerar", methods=["POST"])
def gerar_dados():
    from app.dados_entrada.gerador_dados import GeracaoDadosError, gerar

    dados = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(gerar(dados, db.listar_zonas(apenas_ativas=True))), 201
    except (GeracaoDadosError, dados_db.ConfiguracaoDadosEntradaError):
        return jsonify({"erro": "Não foi possível gerar os dados de entrada informados."}), 400
    except Exception:
        current_app.logger.exception("Falha inesperada ao gerar dados de entrada")
        return jsonify({"erro": MENSAGEM_ERRO_INTERNO}), 500


@dados_entrada_leitura_bp.route("/api/dados-entrada/execucoes", methods=["GET"])
def listar_execucoes():
    return jsonify(
        {
            "execucoes": dados_db.listar_execucoes(),
            "destino": "PostgreSQL (schema dados_entrada)",
        }
    )


@dados_entrada_leitura_bp.route("/api/dados-entrada/exportar.csv", methods=["GET"])
def exportar_csv():
    bruto_id = request.args.get("execucao_id")
    try:
        execucao_id = int(bruto_id) if bruto_id else None
    except ValueError:
        return jsonify({"erro": "execucao_id deve ser inteiro."}), 400
    if execucao_id is not None and dados_db.obter_execucao(execucao_id) is None:
        return jsonify({"erro": f"Execução {execucao_id} não encontrada."}), 404
    colunas, linhas = dados_db.iterar_medicoes_csv(execucao_id)

    def gerar_csv():
        saida = io.StringIO(newline="")
        escritor = csv.writer(saida)
        escritor.writerow(colunas)
        yield "\ufeff" + saida.getvalue()
        for linha in linhas:
            saida.seek(0)
            saida.truncate(0)
            escritor.writerow(linha)
            yield saida.getvalue()

    sufixo = f"_{execucao_id}" if execucao_id is not None else "_todas"
    return Response(
        stream_with_context(gerar_csv()),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="dados_entrada{sufixo}.csv"'},
    )


@dados_entrada_bp.route("/api/dados-entrada/medicoes", methods=["DELETE"])
def excluir_medicoes():
    dados = request.get_json(force=True, silent=True) or {}
    if not confirmacao_de_exclusao_valida(dados):
        return jsonify({"erro": "Digite APAGAR para confirmar a exclusão."}), 400
    execucao_id = dados.get("execucao_id")
    try:
        execucao_id = int(execucao_id) if execucao_id not in (None, "") else None
    except (TypeError, ValueError):
        return jsonify({"erro": "execucao_id deve ser inteiro."}), 400
    apagadas = dados_db.excluir_medicoes(execucao_id)
    return jsonify({"ok": True, "medicoes_apagadas": apagadas})


@dados_entrada_bp.route("/api/dados-entrada/copiar-para-historico", methods=["POST"])
def copiar_para_historico():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        bruto_execucao_id = dados.get("execucao_id")
        if bruto_execucao_id is None:
            raise ValueError
        execucao_id = int(bruto_execucao_id)
        resultado = dados_db.copiar_medicoes_para_historico(execucao_id)
        return jsonify({"ok": True, **resultado})
    except (TypeError, ValueError):
        return jsonify({"erro": "Informe uma execução válida."}), 400
    except dados_db.ConfiguracaoDadosEntradaError:
        return jsonify({"erro": "Os dados de entrada não podem ser copiados com esses parâmetros."}), 400
    except Exception:
        current_app.logger.exception("Falha ao copiar dados de entrada para o histórico")
        return jsonify({"erro": MENSAGEM_ERRO_INTERNO}), 500


@dados_entrada_bp.route("/api/dados-entrada/apagar-historico", methods=["DELETE"])
def apagar_historico():
    dados = request.get_json(force=True, silent=True) or {}
    if not confirmacao_de_exclusao_valida(dados):
        return jsonify({"erro": "Digite APAGAR para confirmar a exclusão."}), 400
    total = db.contar_leituras()
    db.limpar_historico()
    return jsonify({"ok": True, "medicoes_apagadas": total})

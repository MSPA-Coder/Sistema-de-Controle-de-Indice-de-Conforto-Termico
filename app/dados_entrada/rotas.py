"""Rotas de consulta e operacao da aba de dados de entrada."""

from __future__ import annotations

import csv
import io

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from .. import database as db
from ..app_factory import MENSAGEM_ERRO_INTERNO, confirmacao_de_exclusao_valida
from ..seguranca import auth
from ..seguranca.audit_log import registrar_evento_revisavel
from ..seguranca.zonas import filtrar_por_zona, zonas_permitidas
from . import db as dados_db
from .cidades import referencias_publicas

_INICIOS_DE_FORMULA = ("=", "+", "-", "@", "\t", "\r")


def _zonas_ativas_da_conta() -> list[dict]:
    """Zonas ativas que a conta pode ver (administradores veem todas)."""
    return filtrar_por_zona(
        db.listar_zonas(apenas_ativas=True), zonas_permitidas(auth.usuario_atual()), "id"
    )


def _neutralizar_formula(valor):
    """Texto que o Excel/LibreOffice leria como fórmula ganha um `'` na frente.

    Só texto: número negativo é `float`, não `str`, e segue como número.
    """
    if isinstance(valor, str) and valor.startswith(_INICIOS_DE_FORMULA):
        return "'" + valor
    return valor

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
    return jsonify(dados_db.listar_configuracoes(_zonas_ativas_da_conta()))


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
        configuracoes = dados_db.salvar_configuracoes_zonas(zonas, _zonas_ativas_da_conta())
    except dados_db.ConfiguracaoDadosEntradaError:
        return jsonify({"erro": "As configurações de dados de entrada são inválidas."}), 400
    return jsonify(configuracoes)


@dados_entrada_bp.route("/api/dados-entrada/gerar", methods=["POST"])
def gerar_dados():
    from app.dados_entrada.gerador_dados import GeracaoDadosError, gerar

    dados = request.get_json(force=True, silent=True) or {}
    try:
        resultado = gerar(dados, _zonas_ativas_da_conta())
        registrar_evento_revisavel(
            "DADOS_ENTRADA_GERADOS",
            "dados",
            "Gerou dados de entrada",
            detalhes={
                "execucao_id": resultado.get("execucao_id"),
                "total_medicoes": resultado.get("total_medicoes"),
            },
        )
        return jsonify(resultado), 201
    except (GeracaoDadosError, dados_db.ConfiguracaoDadosEntradaError) as erro:
        # As mensagens destas duas exceções são escritas para a pessoa (campo
        # inválido, zona incompleta, limite de medições...). Descartá-las deixava
        # só "Não foi possível gerar", sem dizer o que corrigir.
        detalhe = str(erro).strip()[:300]
        return jsonify(
            {"erro": detalhe or "Não foi possível gerar os dados de entrada informados."}
        ), 400
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
    permitidas = zonas_permitidas(auth.usuario_atual())
    colunas, linhas = dados_db.iterar_medicoes_csv(
        execucao_id, zona_ids=None if permitidas is None else sorted(permitidas)
    )

    def gerar_csv():
        saida = io.StringIO(newline="")
        escritor = csv.writer(saida)
        escritor.writerow(colunas)
        yield "\ufeff" + saida.getvalue()
        for linha in linhas:
            saida.seek(0)
            saida.truncate(0)
            escritor.writerow([_neutralizar_formula(celula) for celula in linha])
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
    registrar_evento_revisavel(
        "MEDICOES_EXCLUIDAS",
        "dados",
        "Excluiu medições de dados de entrada",
        detalhes={"execucao_id": execucao_id, "medicoes_apagadas": apagadas},
    )
    return jsonify({"ok": True, "medicoes_apagadas": apagadas})


@dados_entrada_bp.route("/api/dados-entrada/copiar-para-historico", methods=["POST"])
def copiar_para_historico():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        bruto_execucao_id = dados.get("execucao_id")
        if bruto_execucao_id is None:
            raise ValueError
        execucao_id = int(bruto_execucao_id)
        permitidas = zonas_permitidas(auth.usuario_atual())
        if permitidas is not None and not dados_db.zonas_da_execucao(execucao_id) <= permitidas:
            # A cópia é da execução inteira (e idempotente): quem não enxerga
            # todas as zonas dela não pode publicá-la.
            return jsonify({"erro": "Seu perfil não tem acesso a esta função."}), 403
        resultado = dados_db.copiar_medicoes_para_historico(execucao_id)
        registrar_evento_revisavel(
            "DADOS_COPIADOS_PARA_HISTORICO",
            "dados",
            "Copiou dados de entrada para o histórico",
            detalhes={"execucao_id": execucao_id, "novas_copiadas": resultado["novas_copiadas"]},
        )
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
    registrar_evento_revisavel(
        "HISTORICO_APAGADO",
        "dados",
        "Apagou o histórico de leituras",
        detalhes={"leituras_apagadas": total},
    )
    return jsonify({"ok": True, "medicoes_apagadas": total})

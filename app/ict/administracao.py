"""Administração pública do ICT.

Cadastro, configurações e manutenção persistem no PostgreSQL. A única ação
que precisa do hardware, o teste de conexão, atravessa a API privada do
coletor pelo mesmo cliente interno utilizado pela aba Operação.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from app.seguranca.audit_log import registrar_evento_revisavel
from app.termico import agregacao

from .. import database as db
from ..app_factory import confirmacao_de_exclusao_valida
from ..models import senha_smtp_configurada
from .coletor_client import chamar_coletor

administracao_bp = Blueprint("administracao", __name__)

CHAVES_CONFIGURACOES_NAO_TECNICAS = frozenset(
    {
        "coletarDados",
        "habilitarSons",
        "enviarEmails",
        "emailDestino",
        "statusMinimoEmail",
        "modoPontoOrvalho",
        "modoUmidadeRelativa",
        "especie",
        "indice",
    }
)


def _configuracoes_publicas(config: dict) -> dict:
    """Nunca deixa a senha SMTP sair do servidor.

    `config` (vindo do banco) nunca TEM `smtpSenha` -- ela não mora mais lá
    (CT-03). `smtpSenhaConfigurada` reflete se a senha resolve por segredo do
    Compose ou variável de ambiente, não o banco; a tela só precisa saber SE
    há senha, nunca qual é.
    """
    publico = dict(config)
    publico["smtpSenhaConfigurada"] = senha_smtp_configurada()
    publico["smtpSenha"] = ""
    return publico


# ---------------------------------------------------------------------------
# Configuracoes e reset
# ---------------------------------------------------------------------------
@administracao_bp.route(
    "/api/manutencao/atualizar-agregados-historicos", methods=["POST"]
)
def atualizar_agregados_historicos():
    """Recalcula somente agregados pendentes; nunca remove leituras brutas."""
    try:
        resultados = agregacao.executar()
        registrar_evento_revisavel(
            "AGREGADOS_HISTORICOS_ATUALIZADOS",
            "manutencao",
            "Atualizou agregados históricos pendentes",
            detalhes={"zonas_processadas": len(resultados)},
        )
        return jsonify({"ok": True, "resultados": resultados})
    except Exception:
        from ..app_factory import MENSAGEM_ERRO_INTERNO

        current_app.logger.exception("Falha ao atualizar os agregados historicos")
        return jsonify({"ok": False, "erro": MENSAGEM_ERRO_INTERNO}), 500


@administracao_bp.route("/api/configuracoes", methods=["GET"])
def obter_configuracoes():
    return jsonify(_configuracoes_publicas(db.obter_configuracoes()))


@administracao_bp.route("/api/configuracoes", methods=["POST"])
def salvar_configuracoes():
    dados = request.get_json(force=True, silent=True) or {}
    from app.seguranca import auth

    usuario = auth.usuario_atual()
    perfil = usuario["perfil"] if usuario else ""
    if not auth.area_permitida(perfil, "sistema"):
        chaves_tecnicas = set(dados) - CHAVES_CONFIGURACOES_NAO_TECNICAS
        if chaves_tecnicas:
            return jsonify({"erro": "Seu perfil não pode alterar configurações técnicas."}), 403
    salvas = db.salvar_configuracoes(dados)
    registrar_evento_revisavel(
        "CONFIGURACOES_ATUALIZADAS",
        "configuracao",
        "Atualizou configurações",
        detalhes={"chaves": sorted(dados)},
    )
    return jsonify(_configuracoes_publicas(salvas))


@administracao_bp.route("/api/reset", methods=["POST"])
def reset():
    """Apaga todo o historico persistido. O grafico ao vivo do coletor
    (buffer em memoria, limitado a poucas dezenas de pontos por zona) NAO
    e limpo na hora -- ele se auto-corrige sozinho dentro de poucos
    ciclos automaticos, conforme novos pontos empurram os antigos para
    fora do buffer. Trade-off deliberado: nao vale a pena outra chamada
    de rede/token para um efeito puramente cosmetico e de curtissima
    duracao numa acao administrativa rara.

    A mesma exclusao que `/api/dados-entrada/apagar-historico` faz -- e a
    mesma trava: confirmacao validada aqui, nao so no `confirm()` do
    navegador (ver `app_factory.confirmacao_de_exclusao_valida`)."""
    dados = request.get_json(force=True, silent=True) or {}
    if not confirmacao_de_exclusao_valida(dados):
        return jsonify({"erro": "Digite APAGAR para confirmar a exclusão."}), 400
    db.limpar_historico()
    registrar_evento_revisavel(
        "HISTORICO_LIMPO", "dados", "Removeu medições e agregados históricos"
    )
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Cadastro: zonas e equipamentos
# ---------------------------------------------------------------------------
@administracao_bp.route("/api/zonas", methods=["POST"])
def criar_zona():
    dados = request.get_json(force=True, silent=True) or {}
    try:
        zona = db.criar_zona(dados)
        registrar_evento_revisavel(
            "ZONA_CRIADA", "cadastro", "Criou zona", detalhes={"zona_id": zona["id"]}
        )
        return jsonify(zona), 201
    except db.ZonaInvalidaError:
        return jsonify({"erro": "Os dados da zona são inválidos."}), 400


@administracao_bp.route("/api/zonas/<int:zona_id>", methods=["GET"])
def obter_zona(zona_id):
    zona = db.obter_zona(zona_id)
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    return jsonify(zona)


@administracao_bp.route("/api/zonas/<int:zona_id>", methods=["PUT"])
def atualizar_zona(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        zona = db.atualizar_zona(zona_id, dados)
    except db.ZonaInvalidaError:
        return jsonify({"erro": "Os dados da zona são inválidos."}), 400
    if zona is None:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    registrar_evento_revisavel(
        "ZONA_ATUALIZADA", "cadastro", "Atualizou zona", detalhes={"zona_id": zona_id}
    )
    return jsonify(zona)


@administracao_bp.route("/api/zonas/<int:zona_id>", methods=["DELETE"])
def excluir_zona(zona_id):
    if not db.excluir_zona(zona_id):
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    # Ver docstring do modulo: a limpeza do estado em memoria do coletor
    # para esta zona acontece no proximo ciclo automatico dele, nao aqui.
    registrar_evento_revisavel(
        "ZONA_EXCLUIDA", "cadastro", "Excluiu zona", detalhes={"zona_id": zona_id}
    )
    return jsonify({"ok": True})


@administracao_bp.route("/api/zonas/<int:zona_id>/equipamentos", methods=["POST"])
def criar_equipamento(zona_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        equipamento = db.criar_equipamento(zona_id, dados)
        registrar_evento_revisavel(
            "EQUIPAMENTO_CRIADO",
            "cadastro",
            "Criou equipamento",
            detalhes={"zona_id": zona_id, "equipamento_id": equipamento["id"]},
        )
        return jsonify(equipamento), 201
    except db.ZonaNaoEncontradaError:
        return jsonify({"erro": f"Zona {zona_id} não encontrada."}), 404
    except db.ZonaInvalidaError:
        return jsonify({"erro": "Os dados do equipamento são inválidos."}), 400


@administracao_bp.route(
    "/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>", methods=["PUT"]
)
def atualizar_equipamento(zona_id, equipamento_id):
    dados = request.get_json(force=True, silent=True) or {}
    try:
        equipamento = db.atualizar_equipamento(equipamento_id, dados)
    except db.ZonaInvalidaError:
        return jsonify({"erro": "Os dados do equipamento são inválidos."}), 400
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404
    registrar_evento_revisavel(
        "EQUIPAMENTO_ATUALIZADO",
        "cadastro",
        "Atualizou equipamento",
        detalhes={"zona_id": zona_id, "equipamento_id": equipamento_id},
    )
    return jsonify(equipamento)


@administracao_bp.route(
    "/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>", methods=["DELETE"]
)
def excluir_equipamento(zona_id, equipamento_id):
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404
    db.excluir_equipamento(equipamento_id)
    registrar_evento_revisavel(
        "EQUIPAMENTO_EXCLUIDO",
        "cadastro",
        "Excluiu equipamento",
        detalhes={"zona_id": zona_id, "equipamento_id": equipamento_id},
    )
    return jsonify({"ok": True})


@administracao_bp.route("/api/auditoria", methods=["GET"])
def listar_auditoria():
    try:
        limite = int(request.args.get("limite", 100))
    except ValueError:
        return jsonify({"erro": "Parâmetro 'limite' precisa ser inteiro."}), 400
    return jsonify({"eventos": db.listar_eventos_auditoria(limite)})


# ---------------------------------------------------------------------------
# Teste de conexao -- unica rota deste modulo que precisa do coletor
# ---------------------------------------------------------------------------
def _equipamento_da_zona_ou_none(zona_id: int, equipamento_id: int) -> dict | None:
    equipamento = db.obter_equipamento(equipamento_id)
    if equipamento is None or equipamento["zona_id"] != zona_id:
        return None
    return equipamento


@administracao_bp.route(
    "/api/zonas/<int:zona_id>/equipamentos/<int:equipamento_id>/testar-conexao", methods=["POST"]
)
def testar_conexao_equipamento(zona_id, equipamento_id):
    equipamento = _equipamento_da_zona_ou_none(zona_id, equipamento_id)
    if equipamento is None:
        return jsonify(
            {"erro": f"Equipamento {equipamento_id} não encontrado na zona {zona_id}."}
        ), 404

    return chamar_coletor(
        f"/api/interno/zonas/{zona_id}/equipamentos/{equipamento_id}/testar-conexao",
        metodo="POST",
        dados={},
    )

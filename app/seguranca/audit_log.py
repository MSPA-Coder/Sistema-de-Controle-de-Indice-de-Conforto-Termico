"""Audit logging para eventos de segurança e operações críticas.

Módulo responsável por registrar eventos de segurança, autenticação,
autorização e operações sensíveis em formato estruturado JSON para
facilitar análise forense e detecção de anomalias.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from typing import Any

from sharedauth.logs import sanitizar_log

# Logger dedicado para auditoria
audit_logger = logging.getLogger("conforto_termico.audit")
audit_logger.setLevel(logging.INFO)

# Sem handler próprio: os registros sobem para o logger raiz, que o Compose
# entrega ao stdout do contêiner junto com o resto dos logs da aplicação.


def _obter_contexto_requisicao() -> dict[str, Any]:
    """Obtém contexto da requisição atual (se disponível)."""
    try:
        from flask import request

        return {
            "ip": request.remote_addr or "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown")[:100],
            "path": request.path,
            "method": request.method,
        }
    except RuntimeError:
        # Fora do contexto Flask
        return {"ip": "unknown", "user_agent": "unknown", "path": "unknown", "method": "unknown"}


def _obter_usuario_atual() -> dict[str, Any]:
    """Obtém informações do usuário atual (se disponível)."""
    try:
        from flask import g, session

        # A sessao guarda so `usuario_id` (e a marca da senha): ler `usuario_login`
        # e `usuario_perfil` dela devolvia sempre `unknown`. Quem a requisicao
        # autenticou e `g.usuario`, carregado pelo hook de login.
        usuario = getattr(g, "usuario", None)
        if usuario:
            return {
                "id": usuario.get("id"),
                "login": usuario.get("login") or "unknown",
                "perfil": usuario.get("perfil") or "unknown",
            }
        usuario_id = session.get("usuario_id")
        if usuario_id:
            return {"id": usuario_id, "login": "unknown", "perfil": "unknown"}
    except (RuntimeError, AttributeError):
        pass

    return {"id": None, "login": "anonymous", "perfil": "none"}


def log_evento(
    evento: str,
    categoria: str,
    acao: str,
    sucesso: bool = True,
    detalhes: dict[str, Any] | None = None,
) -> None:
    """Registra evento de auditoria em formato JSON estruturado.

    Args:
        evento: Nome único do evento (ex: "LOGIN_SUCESSO", "LOGIN_FALHA")
        categoria: Categoria do evento (ex: "autenticacao", "autorizacao", "dados")
        acao: Descrição da ação executada
        sucesso: Se a ação foi bem-sucedida
        detalhes: Detalhes adicionais do evento (dados sensíveis serão sanitizados)
    """
    registro = {
        "timestamp": datetime.now(UTC).isoformat(),
        "evento": evento,
        "categoria": categoria,
        "acao": acao,
        "sucesso": sucesso,
        "contexto": _obter_contexto_requisicao(),
        "usuario": _obter_usuario_atual(),
        "detalhes": _sanitizar_detalhes(detalhes or {}),
        "hostname": os.environ.get("HOSTNAME", "unknown"),
        "thread": threading.current_thread().name,
    }

    if sucesso:
        audit_logger.info(json.dumps(registro, ensure_ascii=False))
    else:
        audit_logger.warning(json.dumps(registro, ensure_ascii=False))


def registrar_evento_revisavel(
    evento: str,
    categoria: str,
    acao: str,
    *,
    detalhes: dict[str, Any] | None = None,
    sucesso: bool = True,
    ator: dict[str, Any] | None = None,
) -> None:
    """Registra uma mutação relevante no log operacional e na trilha da UI.

    Não é usado para visualizações, polling ou leituras de dados: esses eventos
    não agregam valor à revisão e tornariam a trilha inutilmente ruidosa.

    `ator` (`id`, `login`, `perfil`) vale quando a requisição ainda não tem
    `g.usuario` -- o login, que é quem cria a sessão.
    """
    detalhes_seguros = _sanitizar_detalhes(detalhes or {})
    contexto = _obter_contexto_requisicao()
    usuario = ator or _obter_usuario_atual()
    log_evento(evento, categoria, acao, sucesso=sucesso, detalhes=detalhes_seguros)
    from ..database.auditoria import registrar_evento_auditoria

    try:
        registrar_evento_auditoria(
            evento=evento,
            categoria=categoria,
            acao=acao,
            sucesso=sucesso,
            ator_id=usuario["id"],
            ator_login=usuario["login"],
            ator_perfil=usuario["perfil"],
            contexto=contexto,
            detalhes=detalhes_seguros,
        )
    except Exception:
        # A mutação já foi concluída antes desta chamada. Não a transforme em
        # aparente falha por indisponibilidade da trilha; o JSON acima ainda
        # permanece no log operacional para investigação e o erro é visível.
        audit_logger.exception("Falha ao persistir evento de auditoria revisável")


def _sanitizar_detalhes(detalhes: dict[str, Any]) -> dict[str, Any]:
    """Sanitiza dados sensíveis dos detalhes do log.

    Remove ou mascara campos que podem conter informações sensíveis
    como senhas, tokens, segredos, etc.
    """
    campos_sensiveis = frozenset(
        {
            "senha",
            "password",
            "passwd",
            "token",
            "secret",
            "chave",
            "key",
            "authorization",
            "cookie",
            "session_id",
            "csrf_token",
        }
    )

    padrao_mascara = "***REDACTED***"

    def _sanitizar_valor(chave: str, valor: Any) -> Any:
        chave_lower = chave.lower()
        if any(sensivel in chave_lower for sensivel in campos_sensiveis):
            return padrao_mascara

        if isinstance(valor, dict):
            return {k: _sanitizar_valor(k, v) for k, v in valor.items()}

        if isinstance(valor, (list, tuple)):
            return [_sanitizar_valor(f"item_{i}", v) for i, v in enumerate(valor)]

        return valor

    return {chave: _sanitizar_valor(chave, valor) for chave, valor in detalhes.items()}


# Eventos pré-definidos para padronização. Só existe constante para evento
# que alguém emite -- acrescente aqui ao acrescentar o `log_*` correspondente.
class EventosAuditoria:
    """Constantes de eventos de auditoria."""

    # Autenticação
    LOGIN_SUCESSO = "LOGIN_SUCESSO"
    LOGIN_FALHA = "LOGIN_FALHA"
    LOGOUT = "LOGOUT"


def log_login_sucesso(usuario_id: int, login: str, perfil: str = "unknown") -> None:
    """Registra login bem-sucedido (log e trilha da UI)."""
    registrar_evento_revisavel(
        EventosAuditoria.LOGIN_SUCESSO,
        "autenticacao",
        f"Usuário {login} realizou login com sucesso",
        detalhes={"usuario_id": usuario_id, "login": login},
        ator={"id": usuario_id, "login": login, "perfil": perfil},
    )


def log_login_falha(login: str, motivo: str, conta_existe: bool = True) -> None:
    """Registra falha de login.

    O login vem do formulário, então é texto de terceiro: sem `sanitizar_log`,
    quem digitasse uma quebra de linha no campo escreveria uma linha inteira
    de log por conta própria -- e este registro em particular é o que alguém
    vai ler depois de uma tentativa de invasão.

    Só uma conta que existe tem o login gravado: quem digita a senha (ou outro
    texto) no campo de login por engano não a deixa na trilha, e a tabela não
    guarda texto arbitrário de quem não está autenticado.
    """
    login_seguro = sanitizar_log(login)[:80] if conta_existe else "(login inexistente)"
    registrar_evento_revisavel(
        EventosAuditoria.LOGIN_FALHA,
        "autenticacao",
        f"Tentativa de login falhou para {login_seguro}",
        detalhes={"login": login_seguro, "motivo": motivo},
        sucesso=False,
    )

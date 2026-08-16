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
        from flask import session

        usuario_id = session.get("usuario_id")
        usuario_login = session.get("usuario_login")
        usuario_perfil = session.get("usuario_perfil")

        if usuario_id:
            return {
                "id": usuario_id,
                "login": usuario_login or "unknown",
                "perfil": usuario_perfil or "unknown",
            }
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


def log_login_sucesso(usuario_id: int, login: str) -> None:
    """Registra login bem-sucedido."""
    log_evento(
        evento=EventosAuditoria.LOGIN_SUCESSO,
        categoria="autenticacao",
        acao=f"Usuário {login} realizou login com sucesso",
        sucesso=True,
        detalhes={"usuario_id": usuario_id, "login": login},
    )


def log_login_falha(login: str, motivo: str) -> None:
    """Registra falha de login."""
    log_evento(
        evento=EventosAuditoria.LOGIN_FALHA,
        categoria="autenticacao",
        acao=f"Tentativa de login falhou para {login}",
        sucesso=False,
        detalhes={"login": login, "motivo": motivo},
    )

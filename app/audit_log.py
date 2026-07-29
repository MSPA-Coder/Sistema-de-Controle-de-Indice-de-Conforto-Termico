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
from datetime import datetime, timezone
from typing import Any

# Logger dedicado para auditoria
audit_logger = logging.getLogger("conforto_termico.audit")
audit_logger.setLevel(logging.INFO)

# Handler padrão (será configurado pelo app_factory)
_handler_configurado = False


def configurar_audit_log(arquivo_saida: str | None = None) -> None:
    """Configura handler para audit log.

    Args:
        arquivo_saida: Caminho do arquivo de log. Se None, usa stdout.
    """
    global _handler_configurado

    if _handler_configurado:
        return

    # Remove handlers existentes
    audit_logger.handlers.clear()

    if arquivo_saida:
        handler = logging.FileHandler(arquivo_saida, encoding="utf-8")
    else:
        handler = logging.StreamHandler()

    # Formato JSON estruturado
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)

    audit_logger.addHandler(handler)
    audit_logger.propagate = False
    _handler_configurado = True


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
    usuario: dict[str, Any] | None = None,
) -> None:
    """Registra evento de auditoria em formato JSON estruturado.

    Args:
        evento: Nome único do evento (ex: "LOGIN_SUCESSO", "USUARIO_CRIADO")
        categoria: Categoria do evento (ex: "autenticacao", "autorizacao", "dados")
        acao: Descrição da ação executada
        sucesso: Se a ação foi bem-sucedida
        detalhes: Detalhes adicionais do evento (dados sensíveis serão sanitizados)
        usuario: Informações do usuário (obtidas automaticamente se None)
    """
    registro = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evento": evento,
        "categoria": categoria,
        "acao": acao,
        "sucesso": sucesso,
        "contexto": _obter_contexto_requisicao(),
        "usuario": usuario or _obter_usuario_atual(),
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
    CAMPOS_SENSIVEIS = frozenset(
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

    PADRAO_MASCARA = "***REDACTED***"

    def _sanitizar_valor(chave: str, valor: Any) -> Any:
        chave_lower = chave.lower()
        if any(sensivel in chave_lower for sensivel in CAMPOS_SENSIVEIS):
            return PADRAO_MASCARA

        if isinstance(valor, dict):
            return {k: _sanitizar_valor(k, v) for k, v in valor.items()}

        if isinstance(valor, (list, tuple)):
            return [_sanitizar_valor(f"item_{i}", v) for i, v in enumerate(valor)]

        return valor

    return {chave: _sanitizar_valor(chave, valor) for chave, valor in detalhes.items()}


# Eventos pré-definidos para padronização
class EventosAuditoria:
    """Constantes de eventos de auditoria."""

    # Autenticação
    LOGIN_SUCESSO = "LOGIN_SUCESSO"
    LOGIN_FALHA = "LOGIN_FALHA"
    LOGOUT = "LOGOUT"
    SENHA_ALTERADA = "SENHA_ALTERADA"
    TOKEN_CRIADO = "TOKEN_CRIADO"
    TOKEN_REVOGADO = "TOKEN_REVOGADO"

    # Autorização
    ACESSO_PERMITIDO = "ACESSO_PERMITIDO"
    ACESSO_NEGADO = "ACESSO_NEGADO"
    PERMISSAO_CONCEDIDA = "PERMISSAO_CONCEDIDA"
    PERMISSAO_REVOGADA = "PERMISSAO_REVOGADA"

    # Usuários
    USUARIO_CRIADO = "USUARIO_CRIADO"
    USUARIO_ATUALIZADO = "USUARIO_ATUALIZADO"
    USUARIO_REMOVIDO = "USUARIO_REMOVIDO"
    USUARIO_ATIVADO = "USUARIO_ATIVADO"
    USUARIO_DESATIVADO = "USUARIO_DESATIVADO"

    # Dados sensíveis
    CONFIGURACAO_ALTERADA = "CONFIGURACAO_ALTERADA"
    DADOS_EXPORTADOS = "DADOS_EXPORTADOS"
    BACKUP_CRIADO = "BACKUP_CRIADO"
    BACKUP_RESTITUIDO = "BACKUP_RESTITUIDO"

    # Segurança
    RATE_LIMIT_EXCEDIDO = "RATE_LIMIT_EXCEDIDO"
    CIRCUIT_BREAKER_ABERTO = "CIRCUIT_BREAKER_ABERTO"
    TENTATIVA_INJECAO = "TENTATIVA_INJECAO"
    UPLOAD_BLOQUEADO = "UPLOAD_BLOQUEADO"


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


def log_acesso_negado(recurso: str, usuario_login: str, perfil_necessario: str) -> None:
    """Registra acesso negado por autorização."""
    log_evento(
        evento=EventosAuditoria.ACESSO_NEGADO,
        categoria="autorizacao",
        acao=f"Acesso negado ao recurso {recurso}",
        sucesso=False,
        detalhes={
            "recurso": recurso,
            "usuario_login": usuario_login,
            "perfil_necessario": perfil_necessario,
        },
    )


def log_alteracao_sensivel(operacao: str, entidade: str, entidade_id: int, usuario_login: str) -> None:
    """Registra alteração em dado sensível."""
    log_evento(
        evento=EventosAuditoria.CONFIGURACAO_ALTERADA,
        categoria="dados",
        acao=f"{operacao} em {entidade} #{entidade_id}",
        sucesso=True,
        detalhes={
            "operacao": operacao,
            "entidade": entidade,
            "entidade_id": entidade_id,
            "usuario": usuario_login,
        },
    )

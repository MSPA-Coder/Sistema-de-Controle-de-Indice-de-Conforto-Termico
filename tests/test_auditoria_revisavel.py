"""Contratos da trilha de auditoria que aparece para administradores."""

from __future__ import annotations

from app.seguranca import audit_log


def test_evento_revisavel_persiste_ator_contexto_e_oculta_segredo(monkeypatch, app):
    recebido = {}

    monkeypatch.setattr(audit_log, "log_evento", lambda *args, **kwargs: None)

    def registrar(**kwargs):
        recebido.update(kwargs)

    from app.database import auditoria as database_auditoria

    monkeypatch.setattr(database_auditoria, "registrar_evento_auditoria", registrar)
    with app.test_request_context("/api/zonas", method="POST", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        from flask import session

        session.update(usuario_id=7, usuario_login="admin", usuario_perfil="administrador")
        audit_log.registrar_evento_revisavel(
            "ZONA_CRIADA", "cadastro", "Criou zona", detalhes={"senha": "nunca"}
        )

    assert recebido["ator_id"] == 7
    assert recebido["ator_login"] == "admin"
    assert recebido["contexto"]["ip"] == "127.0.0.1"
    assert recebido["contexto"]["path"] == "/api/zonas"
    assert recebido["detalhes"]["senha"] == "***REDACTED***"

"""Deduplicação, lease e retry persistentes, sem enviar e-mail externo."""

import datetime

import pytest

from app.nucleo import notificacoes as n


@pytest.fixture(autouse=True)
def outbox(banco):
    with banco() as conn:
        conn.execute("TRUNCATE notificacoes_outbox RESTART IDENTITY")
    return banco


def estado(banco, item_id):
    with banco(escrita=False) as conn:
        return dict(conn.execute("SELECT * FROM notificacoes_outbox WHERE id=?", (item_id,)).fetchone())


def test_deduplicacao_sobrevive_nova_fila_e_sucesso_nao_reabre(outbox, monkeypatch):
    id1 = n._enfileirar_outbox("qa@example.invalid", "Calor", {"host": "smtp.invalid"})
    assert n._enfileirar_outbox("qa@example.invalid", "Calor", {"host": "smtp.invalid"}) == id1
    itens = n._reivindicar_outbox()
    assert len(itens) == 1 and itens[0]["tentativas"] == 1
    assert n._reivindicar_outbox() == []
    monkeypatch.setattr(n.Email, "enviar", lambda self, config: True)
    n.FilaNotificacoes()._enviar(itens[0])
    assert estado(outbox, id1)["status"] == "enviado"
    assert estado(outbox, id1)["enviado_em"]
    assert n._enfileirar_outbox("qa@example.invalid", "Calor", {"host": "smtp.invalid"}) == id1
    assert n._reivindicar_outbox() == []


@pytest.mark.parametrize("falha", ["recusa", "excecao"])
def test_retry_adia_envio_e_esgota_sem_perder_auditoria(outbox, monkeypatch, falha):
    def enviar(self, config):
        if falha == "excecao":
            raise OSError("SMTP indisponível")
        return False

    monkeypatch.setattr(n.Email, "enviar", enviar)
    item_id = n._enfileirar_outbox("qa@example.invalid", "Alerta", {})
    worker = n.FilaNotificacoes()
    for tentativa in range(1, n.MAX_TENTATIVAS_OUTBOX + 1):
        (item,) = n._reivindicar_outbox()
        assert item["tentativas"] == tentativa
        worker._enviar(item)
        salvo = estado(outbox, item_id)
        assert salvo["ultimo_erro"]
        assert salvo["bloqueado_em"] is None
        assert n._reivindicar_outbox() == []
        if tentativa < n.MAX_TENTATIVAS_OUTBOX:
            assert salvo["status"] == "pendente"
            assert datetime.datetime.fromisoformat(salvo["proxima_tentativa_em"]) > datetime.datetime.now(datetime.UTC)
            with outbox() as conn:
                conn.execute("UPDATE notificacoes_outbox SET proxima_tentativa_em=NULL WHERE id=?", (item_id,))
        else:
            assert salvo["status"] == "falhou"
            assert salvo["proxima_tentativa_em"] is None


def test_lease_expirado_recupera_trabalho_apos_interrupcao(outbox):
    item_id = n._enfileirar_outbox("qa@example.invalid", "Reinício", {})
    assert n._reivindicar_outbox()[0]["id"] == item_id
    antigo = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=6)).isoformat()
    with outbox() as conn:
        conn.execute("UPDATE notificacoes_outbox SET bloqueado_em=? WHERE id=?", (antigo, item_id))
    (recuperado,) = n._reivindicar_outbox()
    assert recuperado["id"] == item_id
    assert recuperado["tentativas"] == 2
    n._concluir_outbox(item_id)
    assert n._reivindicar_outbox() == []


@pytest.mark.parametrize("status,enfileira", [("Conforto", False), ("Alerta", False), ("Perigo", True), ("Emergencia", True)])
def test_piso_de_alerta_persiste_somente_eventos_elegiveis(outbox, status, enfileira):
    resposta = {"indice": "ITU", "valor": 80, "status": status, "zona_id": 42,
                "zona_nome": "QA", "entradas": {"tbs": 35, "tbu": 25}}
    n.notificar_zona_automatico(resposta, {"enviarEmails": True, "statusMinimoEmail": "perigo",
                                        "emailDestino": "qa@example.invalid"})
    itens = n._reivindicar_outbox()
    assert len(itens) == int(enfileira)
    if enfileira:
        assert resposta["email"]["enfileirado"]
        assert itens[0]["destino"] == "qa@example.invalid"
        assert "senha" not in itens[0]["smtp_config"]

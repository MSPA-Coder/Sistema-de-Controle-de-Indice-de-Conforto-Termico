"""A fila de e-mail sobrevive ao tempo ocioso.

Até 24/09/2026 o laço chamava `task_done()` também depois de um `queue.Empty`:
a thread morria com ValueError no primeiro segundo sem item, e dali em diante
nenhum e-mail saía -- nem os que ficavam no outbox. Produção registrava o
traceback a cada subida do coletor.
"""

from __future__ import annotations

import time

from app.nucleo import notificacoes


def test_thread_continua_viva_depois_de_ficar_ociosa(monkeypatch):
    chamadas = []
    monkeypatch.setattr(notificacoes, "_reivindicar_outbox", lambda: chamadas.append(1) or [])

    fila = notificacoes.FilaNotificacoes()
    fila.iniciar()
    try:
        time.sleep(2.5)  # dois ciclos ociosos de 1 s
        assert fila._thread is not None and fila._thread.is_alive()
        assert len(chamadas) >= 2, "o laço deveria acordar e varrer o outbox a cada segundo"
    finally:
        fila.parar()


def test_item_retirado_da_fila_e_marcado_como_feito(monkeypatch):
    monkeypatch.setattr(notificacoes, "_reivindicar_outbox", list)

    fila = notificacoes.FilaNotificacoes()
    fila.iniciar()
    try:
        fila._fila.put(42)
        fila._fila.join()  # só retorna se o laço chamou task_done para o item
        assert fila._thread.is_alive()
    finally:
        fila.parar()

"""SIGTERM (docker stop, deploy) precisa rodar a limpeza do coletor.

Sem manipulador o Python morre ao receber SIGTERM sem executar o `finally` de
`executar_coletor`: a malha por zona e a fila de notificacoes nao paravam, e o
`stop_grace_period` do Compose nao tinha efeito.
"""

from __future__ import annotations

import os
import signal
import sys
import time

import pytest

from app.app_factory import AppConfig, executar_coletor

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM real so existe no POSIX")


class _Parada:
    def __init__(self, nome: str, chamadas: list[str]) -> None:
        self.nome = nome
        self.chamadas = chamadas

    def iniciar(self, _logger) -> None:
        self.chamadas.append(f"{self.nome}.iniciar")

    def parar(self) -> None:
        self.chamadas.append(f"{self.nome}.parar")


def test_sigterm_no_coletor_roda_a_limpeza_e_sai_com_codigo_zero(app, monkeypatch):
    import waitress

    from app.coletor import estado
    from app.nucleo import notificacoes

    chamadas: list[str] = []
    monkeypatch.setattr(estado, "gerenciador_controle", _Parada("malha", chamadas))
    monkeypatch.setattr(notificacoes, "fila_notificacoes", _Parada("fila", chamadas))

    def servidor_falso(*_args, **_kwargs):
        # Como o `docker stop`: o sinal chega ao processo enquanto ele serve.
        os.kill(os.getpid(), signal.SIGTERM)
        time.sleep(5)  # nao deve chegar aqui
        chamadas.append("servidor.terminou_sozinho")

    monkeypatch.setattr(waitress, "serve", servidor_falso)
    anterior = signal.getsignal(signal.SIGTERM)
    config = AppConfig(
        debug=False, host="127.0.0.1", port=0, threaded=False, max_content_length=1_000_000
    )
    try:
        with pytest.raises(SystemExit) as saida:
            executar_coletor(app, config)
    finally:
        signal.signal(signal.SIGTERM, anterior)

    assert saida.value.code == 0
    assert chamadas == ["fila.iniciar", "malha.iniciar", "malha.parar", "fila.parar"]

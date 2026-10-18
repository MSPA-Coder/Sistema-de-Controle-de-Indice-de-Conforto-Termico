"""Regressões de resposta HTTP e admissão concorrente, sem banco/hardware."""

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Event, Lock
from urllib.error import HTTPError, URLError

import pytest
from flask import Flask

from app.ict import coletor_client
from app.nucleo.circuit_breaker import CircuitBreaker, CircuitBreakerAbertoError


class Relogio:
    def __init__(self):
        self.agora = 0.0

    def __call__(self):
        return self.agora


def falhar():
    raise OSError("dependência sintética indisponível")


def test_abre_apos_limite_e_recupera_sem_retry():
    relogio = Relogio()
    circuito = CircuitBreaker("teste", 2, 30, relogio=relogio)
    for _ in range(2):
        with pytest.raises(OSError):
            circuito.executar(falhar)
    with pytest.raises(CircuitBreakerAbertoError):
        circuito.executar(lambda: "não deve executar")
    relogio.agora = 30
    assert circuito.executar(lambda: "recuperado") == "recuperado"
    assert circuito.executar(lambda: "normal") == "normal"


def test_recuperacao_reserva_limite_antes_de_executar():
    """Antes, só a falha concluída contava; dez chamadas passavam pelo teto 3."""
    relogio = Relogio()
    circuito = CircuitBreaker("teste", 1, 30, 3, relogio=relogio)
    with pytest.raises(OSError):
        circuito.executar(falhar)
    relogio.agora = 30
    liberar, admitidas, trava = Event(), Event(), Lock()
    chamadas = 0

    def operacao():
        nonlocal chamadas
        with trava:
            chamadas += 1
            if chamadas == 3:
                admitidas.set()
        assert liberar.wait(5)
        return True

    with ThreadPoolExecutor(max_workers=10) as executor:
        primeiras = [executor.submit(circuito.executar, operacao) for _ in range(3)]
        try:
            assert admitidas.wait(5)
            outras = [
                executor.submit(circuito.executar, operacao, fallback=lambda: False)
                for _ in range(7)
            ]
            assert [f.result(timeout=2) for f in outras] == [False] * 7
        finally:
            liberar.set()
        assert [f.result(timeout=2) for f in primeiras] == [True] * 3
    assert chamadas == 3


def test_sucesso_antigo_nao_fecha_circuito_reaberto():
    relogio = Relogio()
    circuito = CircuitBreaker("teste", 1, 30, relogio=relogio)
    iniciou, liberar = Event(), Event()

    def lenta():
        iniciou.set()
        assert liberar.wait(5)
        return "antiga"

    with ThreadPoolExecutor(max_workers=1) as executor:
        antiga = executor.submit(circuito.executar, lenta)
        try:
            assert iniciou.wait(5)
            with pytest.raises(OSError):
                circuito.executar(falhar)
        finally:
            liberar.set()
        assert antiga.result(timeout=2) == "antiga"
    with pytest.raises(CircuitBreakerAbertoError):
        circuito.executar(lambda: "não executa")


def test_falha_de_recuperacao_reabre_e_fallback_fica_fora_do_lock():
    relogio = Relogio()
    circuito = CircuitBreaker("teste", 1, 30, relogio=relogio)
    with pytest.raises(OSError):
        circuito.executar(falhar)
    relogio.agora = 30
    assert circuito.executar(falhar, fallback=lambda: "falhou") == "falhou"
    assert (
        circuito.executar(
            lambda: "não executa",
            fallback=lambda: circuito.executar(lambda: "outra dependência", chave="outra"),
        )
        == "outra dependência"
    )


def test_erro_de_programacao_nao_vira_fallback():
    circuito = CircuitBreaker("teste", limite_falhas=1)

    def defeito():
        raise ValueError("contrato incorreto")

    with pytest.raises(ValueError):
        circuito.executar(defeito, fallback=lambda: "não pode esconder")
    assert circuito.executar(lambda: "normal") == "normal"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 429])
def test_recusa_http_preserva_status_e_nao_abre_circuito(monkeypatch, status):
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_CONTROLE", "raiz-sintetica-publica")
    chamadas = 0

    def recusar(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        raise HTTPError(
            "http://coletor.invalid", status, "recusa", {}, BytesIO(b'{"erro":"recusa"}')
        )

    monkeypatch.setattr(coletor_client.urllib.request, "urlopen", recusar)
    with Flask(__name__).app_context():
        for _ in range(6):
            resposta, codigo = coletor_client.chamar_coletor(
                "/api/interno/zonas/1/calcular", metodo="POST"
            )
            assert codigo == status
            assert resposta.get_json() == {"erro": "recusa"}
    assert chamadas == 6


@pytest.mark.parametrize("status", [None, 500, 502, 503, 504])
def test_falha_de_infraestrutura_abre_um_circuito_para_o_coletor(monkeypatch, status):
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_CONTROLE", "raiz-sintetica-publica")
    chamadas = 0

    def indisponivel(*args, **kwargs):
        nonlocal chamadas
        chamadas += 1
        if status is None:
            raise URLError("rede sintética")
        raise HTTPError("http://coletor.invalid", status, "falha", {}, BytesIO(b"{}"))

    monkeypatch.setattr(coletor_client.urllib.request, "urlopen", indisponivel)
    with Flask(__name__).app_context():
        for indice in range(7):
            resposta, codigo = coletor_client.chamar_coletor(
                f"/api/interno/zonas/{indice}/calcular", metodo="POST"
            )
            assert codigo == 502
            assert resposta.get_json()["circuit_breaker"] == "ativo"
    assert chamadas == 5  # não faz retry nem cria circuitos por zona


@pytest.mark.parametrize("corpo", [b"[]", b"texto", b"\xff", b"x" * (1024 * 1024 + 1)])
def test_resposta_invalida_do_coletor_nao_vira_sucesso(monkeypatch, corpo):
    monkeypatch.setenv("CONFORTO_INTERNO_TOKEN_CONTROLE", "raiz-sintetica-publica")

    class Resposta(BytesIO):
        status = 200

    monkeypatch.setattr(coletor_client.urllib.request, "urlopen", lambda *a, **k: Resposta(corpo))
    with Flask(__name__).app_context():
        resposta, codigo = coletor_client.chamar_coletor(
            "/api/interno/zonas/1/calcular", metodo="POST"
        )
        assert codigo == 502
        assert "erro" in resposta.get_json()

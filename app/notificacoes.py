"""
notificacoes.py
================
Fila assincrona de e-mail de alerta, usada pelo ciclo AUTOMATICO de
controle das zonas (`coletor/controle.py`).

Por que uma fila, e nao chamar `Email.enviar` direto do laco: o ciclo
automatico (`GerenciadorControleZonas._loop`) roda numa UNICA thread
cuidando de todas as zonas em sequencia, no intervalo configurado em
`intervaloLeituraSegundos` (minimo de 0.2s). `Email.enviar` faz uma
chamada de rede SINCRONA (`smtplib.SMTP`, timeout de 10s) -- se essa
chamada acontecesse direto no laco, um servidor SMTP fora do ar
atrasaria a leitura e o acionamento de TODAS as outras zonas pelo tempo
do timeout, a cada ciclo com algum alerta pendente. A fila desacopla o
envio (rede, pode falhar/demorar) do calculo+acionamento (tem que rodar
no intervalo configurado, custe o que custar ao e-mail).

O fluxo MANUAL (`coletor/rotas.py:calcular_zona`, disparado por um
tecnico com uma zona em modo manual) continua enviando de forma
SINCRONA -- e uma unica requisicao HTTP isolada (thread do Flask, nao a
thread do laco automatico), entao o risco de bloquear outras zonas nao
existe ali. Por isso esse fluxo ainda devolve `enviado_de_verdade`
(sucesso/falha ja conhecidos na hora da resposta); a fila assincrona,
por definicao, nao sabe o resultado a tempo -- so promete "enfileirado".

As funcoes `deve_notificar_email`, `smtp_config_atual` e
`montar_conteudo_zona` sao compartilhadas pelos dois fluxos para que a
regra de "quando alertar" nunca fique duplicada/divergente entre o
manual e o automatico.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING

from . import thermal_indices as ti
from .models import Email

if TYPE_CHECKING:
    import logging


def deve_notificar_email(resposta: dict, config: dict) -> bool:
    """E-mail so sai se `enviarEmails` estiver ligado E o status
    calculado tiver atingido o piso configurado em `statusMinimoEmail`.
    Mesma regra usada nos dois fluxos (manual e automatico)."""
    if not config.get("enviarEmails"):
        return False
    return ti.status_atinge_minimo(
        resposta.get("status", ""),
        config.get("statusMinimoEmail", "conforto"),
    )


def smtp_config_atual(config: dict) -> dict:
    return {
        "host": config.get("smtpHost") or None,
        "porta": config.get("smtpPorta") or None,
        "usuario": config.get("smtpUsuario") or None,
        "senha": config.get("smtpSenha") or None,
    }


def montar_conteudo_zona(resposta: dict) -> str:
    return Email.montar_conteudo(
        resposta["indice"],
        resposta["valor"],
        resposta["status"],
        resposta.get("entradas"),
        {"id": resposta.get("zona_id"), "nome": resposta.get("zona_nome")},
    )


class FilaNotificacoes:
    """Um worker (thread daemon) processando uma fila FIFO de e-mails
    pendentes, em ordem, um de cada vez. `iniciar`/`parar` seguem o
    mesmo formato de `GerenciadorControleZonas` (`coletor/controle.py`)
    de proposito -- os dois ciclos de vida sao ligados/desligados juntos
    em `app_factory.executar_servidor`.

    Falha ao enviar um item nunca derruba o worker nem propaga para quem
    enfileirou -- fica so registrada no log (quando um `logger` foi
    passado a `iniciar`)."""

    def __init__(self) -> None:
        self._fila: queue.Queue[dict | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._logger: logging.Logger | None = None

    def iniciar(self, logger: logging.Logger | None = None) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._logger = logger
        self._thread = threading.Thread(target=self._loop, name="notificacoes-email", daemon=True)
        self._thread.start()

    def parar(self, timeout: float = 3.0) -> None:
        if self._thread is None:
            return
        self._fila.put(None)  # sentinela: destrava o get() bloqueante do loop
        self._thread.join(timeout=timeout)
        self._thread = None

    def enfileirar(self, destino: str, conteudo: str, smtp_config: dict) -> None:
        self._fila.put({"destino": destino, "conteudo": conteudo, "smtp_config": smtp_config})

    def tamanho(self) -> int:
        return self._fila.qsize()

    def _loop(self) -> None:
        while True:
            item = self._fila.get()
            try:
                if item is None:
                    break
                self._enviar(item)
            finally:
                self._fila.task_done()

    def _enviar(self, item: dict) -> None:
        try:
            email = Email(item["destino"], item["conteudo"])
            enviado = email.enviar(item["smtp_config"])
            if self._logger:
                registrar = self._logger.info if enviado else self._logger.warning
                registrar(
                    "E-mail de alerta automatico %s para %s",
                    "enviado" if enviado else "NAO enviado (ver log de Email.enviar)",
                    item["destino"],
                )
        except Exception:
            if self._logger:
                self._logger.exception(
                    "Falha inesperada ao processar e-mail da fila de notificacoes"
                )


# Uma unica fila por processo -- mesmo padrao de singleton de modulo usado
# em `coletor/estado.py` (gerenciador_controle, zona_service).
fila_notificacoes = FilaNotificacoes()


def notificar_zona_automatico(
    resposta: dict, config: dict, logger: logging.Logger | None = None
) -> dict:
    """Chamada pelo ciclo AUTOMATICO (`controle.py`). Enfileira o envio e
    devolve na hora -- nunca bloqueia o laco de controle esperando o
    SMTP responder. `resposta["email"]` marca "enfileirado", nao
    "enviado": o resultado real do envio so aparece no log do worker."""
    if not deve_notificar_email(resposta, config):
        return resposta
    try:
        conteudo = montar_conteudo_zona(resposta)
        destino = (config.get("emailDestino") or "produtor@fazenda.com.br").strip()
        fila_notificacoes.enfileirar(destino, conteudo, smtp_config_atual(config))
        resposta["email"] = {"destino": destino, "conteudo": conteudo, "enfileirado": True}
    except Exception:
        if logger:
            logger.exception("Falha ao montar e-mail de alerta automatico da zona")
    return resposta

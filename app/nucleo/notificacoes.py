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

import datetime
import hashlib
import json
import queue
import threading
from contextlib import suppress
from typing import TYPE_CHECKING

from app.database.comum import conexao
from app.termico import thermal_indices as ti

from ..models import Email, timestamp_utc

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
    """Host/porta/usuario vem da configuracao persistida; a senha, nao (CT-03).

    Sem a chave `"senha"` aqui, `Email.enviar` cai no proprio fallback
    (`models._resolver_senha_smtp`, segredo do Compose ou `SMTP_PASS`) -- o
    unico lugar que resolve a senha, para nao duplicar essa decisao.
    """
    return {
        "host": config.get("smtpHost") or None,
        "porta": config.get("smtpPorta") or None,
        "usuario": config.get("smtpUsuario") or None,
    }


def montar_conteudo_zona(resposta: dict) -> str:
    return Email.montar_conteudo(
        resposta["indice"],
        resposta["valor"],
        resposta["status"],
        resposta.get("entradas"),
        {"id": resposta.get("zona_id"), "nome": resposta.get("zona_nome")},
    )


MAX_TENTATIVAS_OUTBOX = 5
INTERVALO_RETRY_OUTBOX_SEGUNDOS = 60
TEMPO_BLOQUEIO_OUTBOX_SEGUNDOS = 300


def _chave_deduplicacao(destino: str, conteudo: str, smtp_config: dict) -> str:
    material = json.dumps(
        {"destino": destino, "conteudo": conteudo, "smtp": smtp_config},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _enfileirar_outbox(destino: str, conteudo: str, smtp_config: dict) -> int:
    """Persiste uma notificação antes de acordar o worker.

    A chave é determinística para que ciclos repetidos não gerem uma segunda
    mensagem para o mesmo evento. Itens enviados nunca são reabertos; falhas
    transitórias continuam no mesmo registro para retry e auditoria.
    """
    chave = _chave_deduplicacao(destino, conteudo, smtp_config)
    agora = timestamp_utc()
    with conexao() as conn:
        conn.execute(
            """
            INSERT INTO notificacoes_outbox
                (dedupe_key, destino, conteudo, smtp_config, status, criado_em)
            VALUES (?, ?, ?, ?, 'pendente', ?)
            ON CONFLICT(dedupe_key) DO UPDATE SET
                destino = excluded.destino,
                conteudo = excluded.conteudo,
                smtp_config = excluded.smtp_config
            WHERE notificacoes_outbox.status NOT IN ('enviado', 'enviando')
            """,
            (chave, destino, conteudo, json.dumps(smtp_config), agora),
        )
        linha = conn.execute(
            "SELECT id FROM notificacoes_outbox WHERE dedupe_key = ?", (chave,)
        ).fetchone()
    return int(linha["id"])


def _reivindicar_outbox(limite: int = 10) -> list[dict]:
    agora = datetime.datetime.now(datetime.UTC)
    agora_texto = agora.isoformat(timespec="seconds")
    expirado = (agora - datetime.timedelta(seconds=TEMPO_BLOQUEIO_OUTBOX_SEGUNDOS)).isoformat(
        timespec="seconds"
    )
    limite = max(1, min(100, int(limite)))
    itens = []
    with conexao() as conn:
        conn.execute(
            "UPDATE notificacoes_outbox SET status='pendente', bloqueado_em=NULL "
            "WHERE status='enviando' AND bloqueado_em < ?",
            (expirado,),
        )
        linhas = conn.execute(
            """
            SELECT * FROM notificacoes_outbox
            WHERE status = 'pendente'
              AND (proxima_tentativa_em IS NULL OR proxima_tentativa_em <= ?)
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT ?
            """,
            (agora_texto, limite),
        ).fetchall()
        for linha in linhas:
            conn.execute(
                "UPDATE notificacoes_outbox SET status='enviando', tentativas=tentativas+1, "
                "bloqueado_em=? WHERE id=?",
                (agora_texto, linha["id"]),
            )
            item = dict(linha)
            item["tentativas"] = int(item.get("tentativas") or 0) + 1
            itens.append(item)
    for item in itens:
        if isinstance(item.get("smtp_config"), str):
            try:
                item["smtp_config"] = json.loads(item["smtp_config"])
            except json.JSONDecodeError:
                item["smtp_config"] = {}
        elif not isinstance(item.get("smtp_config"), dict):
            item["smtp_config"] = {}
    return itens


def _concluir_outbox(item_id: int) -> None:
    with conexao() as conn:
        conn.execute(
            "UPDATE notificacoes_outbox SET status='enviado', enviado_em=?, "
            "bloqueado_em=NULL, proxima_tentativa_em=NULL WHERE id=?",
            (timestamp_utc(), item_id),
        )


def _falhar_outbox(item: dict, erro: str) -> None:
    tentativas = int(item.get("tentativas") or 0)
    permanente = tentativas >= MAX_TENTATIVAS_OUTBOX
    proxima = None
    if not permanente:
        proxima = (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=INTERVALO_RETRY_OUTBOX_SEGUNDOS * tentativas)
        ).isoformat(timespec="seconds")
    with conexao() as conn:
        conn.execute(
            "UPDATE notificacoes_outbox SET status=?, proxima_tentativa_em=?, "
            "bloqueado_em=NULL, ultimo_erro=? WHERE id=?",
            ("falhou" if permanente else "pendente", proxima, str(erro)[:1000], item["id"]),
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
        self._fila: queue.Queue[int | None] = queue.Queue()
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
        item_id = _enfileirar_outbox(destino, conteudo, smtp_config)
        self._fila.put(item_id)

    def tamanho(self) -> int:
        return self._fila.qsize()

    def _loop(self) -> None:
        while True:
            try:
                item = self._fila.get(timeout=1.0)
                retirado = True
            except queue.Empty:
                item = 0  # acorda periodicamente para recuperar itens persistidos
                retirado = False
            try:
                if item is None:
                    break
                for pendente in _reivindicar_outbox():
                    self._enviar(pendente)
            finally:
                # `task_done` só para o que saiu da fila. Chamá-lo depois de um
                # `Empty` levantava ValueError e matava a thread no primeiro
                # segundo ocioso -- e o e-mail parava sem aviso.
                if retirado and item is not None:
                    self._fila.task_done()

    def _enviar(self, item: dict) -> None:
        try:
            email = Email(item["destino"], item["conteudo"])
            enviado = email.enviar(item["smtp_config"])
            if enviado:
                _concluir_outbox(item["id"])
            else:
                _falhar_outbox(item, "O servidor SMTP recusou o envio.")
            if self._logger:
                registrar = self._logger.info if enviado else self._logger.warning
                registrar(
                    "E-mail de alerta automatico %s para %s",
                    "enviado" if enviado else "NAO enviado (ver log de Email.enviar)",
                    item["destino"],
                )
        except Exception as erro:
            with suppress(Exception):
                _falhar_outbox(item, str(erro))
                # A falha do próprio banco não pode derrubar o worker; o item
                # permanece com lease expirável para recuperação posterior.
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
        destino = (config.get("emailDestino") or "alertas@example.invalid").strip()
        smtp_config = smtp_config_atual(config)
        fila_notificacoes.enfileirar(destino, conteudo, smtp_config)
        resposta["email"] = {"destino": destino, "conteudo": conteudo, "enfileirado": True}
    except Exception:
        if logger:
            logger.exception("Falha ao montar e-mail de alerta automatico da zona")
    return resposta

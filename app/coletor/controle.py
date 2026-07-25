# -*- coding: utf-8 -*-
"""Malha operacional executada no backend do processo coletor.

O navegador apenas solicita operacoes e consulta o estado persistido. O
ciclo automatico, os bloqueios por zona e o heartbeat pertencem a este
modulo, portanto continuam funcionando mesmo sem uma tela aberta.
"""

from __future__ import annotations

import datetime
import threading
from collections import defaultdict

from .. import agregacao
from .. import database as db
from .. import notificacoes
from .. import thermal_indices as ti
from ..zona_service import ZonaCalculoError


class ZonaOcupadaError(RuntimeError):
    """Uma segunda operacao tentou usar a mesma zona simultaneamente."""


class ModoOperacaoError(ValueError):
    """A operacao solicitada nao e permitida no modo atual da zona."""


class GerenciadorControleZonas:
    def __init__(self, zona_service):
        self.zona_service = zona_service
        self._locks: defaultdict[int, threading.Lock] = defaultdict(threading.Lock)
        self._locks_guard = threading.Lock()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._logger = None
        # IDs de zona vistos no ultimo ciclo automatico -- usado por
        # `_reconciliar_zonas_removidas` para descobrir quais zonas
        # sumiram (excluidas por fora deste processo, ver
        # `ict/administracao.py`) e limpar o estado em memoria
        # correspondente. Comeca vazio de proposito: no PRIMEIRO ciclo,
        # nao ha "zona que sumiu" ainda -- so uma baseline sendo criada.
        self._zonas_conhecidas: set[int] = set()

    def _lock_zona(self, zona_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks[zona_id]

    def _executar_exclusivo(self, zona_id: int, funcao):
        lock = self._lock_zona(zona_id)
        if not lock.acquire(blocking=False):
            raise ZonaOcupadaError(
                f"A zona {zona_id} ja possui um ciclo ou comando em andamento."
            )
        try:
            return funcao()
        finally:
            lock.release()

    @staticmethod
    def _agora() -> datetime.datetime:
        return datetime.datetime.now().replace(microsecond=0)

    @staticmethod
    def _intervalo_segundos() -> float:
        try:
            return max(
                0.2,
                float(db.obter_configuracoes().get("intervaloLeituraSegundos") or 1),
            )
        except (TypeError, ValueError):
            return 1.0

    def iniciar(self, logger=None) -> None:
        """Inicia uma unica thread de coleta; chamadas repetidas sao inertes."""
        if self._thread and self._thread.is_alive():
            return
        self._logger = logger
        self._parar.clear()
        agora = self._agora()
        proximo = agora + datetime.timedelta(seconds=self._intervalo_segundos())
        db.salvar_status_coletor(
            "online",
            iniciado_em=agora.isoformat(timespec="seconds"),
            proximo_ciclo_em=proximo.isoformat(timespec="seconds"),
        )
        self._thread = threading.Thread(
            target=self._loop, name="controle-zonas", daemon=True
        )
        self._thread.start()

    def parar(self, timeout: float = 3.0) -> None:
        self._parar.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        db.salvar_status_coletor("offline", proximo_ciclo_em=None)

    def _loop(self) -> None:
        while not self._parar.is_set():
            intervalo = self._intervalo_segundos()
            proximo = self._agora() + datetime.timedelta(seconds=intervalo)
            db.salvar_status_coletor(
                "online", proximo_ciclo_em=proximo.isoformat(timespec="seconds")
            )
            if self._parar.wait(intervalo):
                break
            try:
                self.executar_ciclo_automatico(logger=self._logger)
            except Exception as erro:  # rede de seguranca da thread
                if self._logger:
                    self._logger.exception("Falha no ciclo automatico de zonas")
                db.salvar_status_coletor("online", erro=str(erro))

    def _reconciliar_zonas_removidas(self) -> None:
        """Limpa o estado em memoria (lock, historico do grafico,
        histerese do resfriador -- ver `ZonaService`) de zonas que
        sumiram de `db.listar_zonas()` desde o ciclo anterior.

        Antes da separacao entre coletor e "outra parte" (ver
        `ict/administracao.py`), excluir uma zona SEMPRE acontecia
        no mesmo processo que mantem esse estado em memoria, e a rota de
        exclusao chamava `limpar_historico_grafico`/`limpar_resfriador`
        diretamente. Agora que o cadastro de zonas pode ser mutado por
        outro processo, esse estado nao seria limpo sozinho -- ficaria
        orfao (nunca mais lido, mas ocupando memoria) ate o processo
        reiniciar. Sem isso tambem existe um segundo risco, mais sutil:
        se uma zona NOVA reaproveitar o mesmo id de uma zona ja excluida
        (o SQLite reaproveita ids de autoincrement em alguns cenarios),
        ela herdaria silenciosamente o historico/histerese da zona
        antiga. Rodar isto uma vez por ciclo (ja e chamado a cada
        `intervaloLeituraSegundos`) resolve os dois problemas sem
        precisar de um mecanismo de notificacao entre processos."""
        ids_atuais = {zona["id"] for zona in db.listar_zonas()}
        removidas = self._zonas_conhecidas - ids_atuais
        for zona_id in removidas:
            self.zona_service.limpar_historico_grafico(zona_id)
            self.zona_service.limpar_resfriador(zona_id)
            with self._locks_guard:
                self._locks.pop(zona_id, None)
        self._zonas_conhecidas = ids_atuais

    def executar_ciclo_automatico(self, logger=None) -> list[dict]:
        """Executa uma passagem apenas pelas zonas ativas em automatico."""
        self._reconciliar_zonas_removidas()
        config = db.obter_configuracoes()
        resultados: list[dict] = []
        for zona in db.listar_zonas(apenas_ativas=True):
            controle = zona.get("controle") or db.obter_controle_zona(zona["id"])
            if not controle or controle.get("modo") != "automatico":
                continue
            try:
                def _calcular_automatico(zona_id=zona["id"]):
                    atual = db.obter_controle_zona(zona_id)
                    if not atual or atual.get("modo") != "automatico":
                        return None
                    return self.zona_service.calcular(zona_id, logger=logger)

                resposta = self._executar_exclusivo(
                    zona["id"],
                    _calcular_automatico,
                )
                if resposta is None:
                    continue
                notificacoes.notificar_zona_automatico(resposta, config, logger=logger)
                resultados.append(resposta)
                db.registrar_evento_operacao(
                    "ciclo_automatico",
                    "calculo_concluido",
                    zona_id=zona["id"],
                    detalhes={
                        "status": resposta.get("status"),
                        "valor": resposta.get("valor"),
                        "qualidade": resposta.get("qualidade"),
                    },
                )
            except (ZonaCalculoError, ti.EntradaInvalidaError, ZonaOcupadaError) as erro:
                mensagem = str(erro)
                db.registrar_falha_operacional_zona(zona["id"], mensagem)
                db.registrar_evento_operacao(
                    "ciclo_automatico",
                    "falha",
                    zona_id=zona["id"],
                    detalhes={"erro": mensagem},
                )
                resultados.append(
                    {"zona_id": zona["id"], "zona_nome": zona["nome"], "erro": mensagem}
                )

        agora = self._agora().isoformat(timespec="seconds")
        db.salvar_status_coletor("online", ultimo_ciclo_em=agora, erro=None)

        # Consolidacao de 15min/hora: idempotente e barata quando nao ha
        # janela pendente (ver docstring de agregacao.py), entao roda a
        # cada ciclo sem exigir um agendador separado.
        try:
            agregacao.executar(logger=logger)
        except Exception:
            if logger:
                logger.exception("Falha na consolidacao periodica (15min/hora)")

        return resultados

    def calcular_manual(
        self, zona_id: int, entradas: dict | None = None, logger=None
    ) -> dict:
        def _calcular():
            controle = db.obter_controle_zona(zona_id)
            if controle is None:
                raise ZonaCalculoError(f"Zona {zona_id} nao encontrada.")
            if controle["modo"] != "manual":
                raise ModoOperacaoError(
                    "O calculo solicitado pela tela so e aceito no modo manual."
                )
            if isinstance(entradas, dict):
                return self.zona_service.calcular_manual(zona_id, entradas, logger=logger)
            return self.zona_service.calcular(zona_id, logger=logger)

        resposta = self._executar_exclusivo(zona_id, _calcular)
        db.registrar_evento_operacao(
            "ciclo_manual",
            "calculo_concluido",
            zona_id=zona_id,
            detalhes={
                "status": resposta.get("status"),
                "valor": resposta.get("valor"),
                "qualidade": resposta.get("qualidade"),
            },
        )
        return resposta

    def alterar_controle(self, zona_id: int, dados: dict, logger=None) -> dict:
        def _alterar():
            anterior = db.obter_controle_zona(zona_id)
            controle = db.salvar_controle_zona(zona_id, dados)
            desligamento = None
            if controle["modo"] in ("desligado", "manutencao"):
                desligamento = self.zona_service.desativar_atuadores(
                    zona_id, logger=logger
                )
                confirmado = desligamento["confirmado"]
                db.salvar_estado_equipamentos(
                    zona_id,
                    bool(confirmado.get("ventilador")),
                    bool(confirmado.get("nebulizador")),
                    None,
                    False,
                    False,
                    confirmado.get("ventilador"),
                    confirmado.get("nebulizador"),
                    desligamento["atuadores_com_falha"],
                    desligamento["qualidade"],
                )
            db.registrar_evento_operacao(
                "configuracao",
                "controle_alterado",
                zona_id=zona_id,
                detalhes={"anterior": anterior, "atual": controle},
            )
            resposta = dict(controle)
            if desligamento:
                resposta["desligamento"] = desligamento
            return resposta

        return self._executar_exclusivo(zona_id, _alterar)

    def comandar_manual(
        self, zona_id: int, tipo: str, ligar: bool, logger=None
    ) -> dict:
        resultado = self._executar_exclusivo(
            zona_id,
            lambda: self.zona_service.comandar_manual(
                zona_id, tipo, ligar, logger=logger
            ),
        )
        db.salvar_comando_manual_atuador(
            zona_id,
            tipo,
            ligar,
            resultado["confirmado"],
            resultado["atuadores_com_falha"],
        )
        db.registrar_evento_operacao(
            "comando_manual",
            f"{tipo}_{'ligar' if ligar else 'desligar'}",
            zona_id=zona_id,
            detalhes={
                "desejado": ligar,
                "confirmado": resultado["confirmado"],
                "falhas": resultado["atuadores_com_falha"],
            },
        )
        return resultado

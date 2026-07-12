# -*- coding: utf-8 -*-
"""
zona_service.py
================
Orquestra o calculo do indice de conforto termico POR ZONA: le todos os
sensores Modbus cadastrados na zona, tira a MEDIA das leituras quando ha
mais de um sensor para o mesmo campo (ex.: duas leituras de tbs viram uma
unica media de tbs), deriva ur/ponto de orvalho a partir de tbs+tbu quando
a zona nao tem sensor dedicado para esses campos, calcula o indice
configurado para a zona -- reaproveitando as mesmas classes de dominio do
fluxo manual (`Temperatura`/`Resfriamento` de models.py) -- e persiste no
historico com o `zona_id`. Tambem aciona os atuadores (ventiladores/
nebulizadores) da zona via Modbus, usando uma instancia de `Resfriamento`
POR ZONA (mesma logica de intensidade/histerese ja usada no fluxo manual,
mas com estado independente por zona: a zona A pode estar em "Perigo"
enquanto a zona B esta em "Conforto").

Uma falha ao ler um sensor especifico ou ao escrever num atuador especifico
nunca derruba o calculo inteiro -- ela fica registrada (sensor: entra na
lista `sensores_com_falha`; atuador: entra em `atuadores_com_falha` e vai
para o log) e o restante do fluxo segue normalmente, seguindo o mesmo
principio de resiliencia ja adotado no resto do projeto (ver
agents.md, "Stability Rules").
"""

from __future__ import annotations

import threading
from typing import Callable

from . import modbus_client
from . import thermal_indices as ti
from .models import Resfriamento, Temperatura


class ZonaCalculoError(ti.EntradaInvalidaError):
    """Erro ao calcular o indice de uma zona: zona inexistente/desativada,
    ou nenhum sensor respondeu com dados suficientes para o indice
    configurado. Subclasse de `EntradaInvalidaError` para reaproveitar o
    mesmo tratamento de erro (400) ja usado na rota /api/calcular."""


def _derivar_campos_calculaveis(entradas: dict, altitude: float) -> dict:
    """Deriva 'ur' e 'tpo' a partir de tbs+tbu quando a zona nao tem sensor
    dedicado para esses campos -- mesma formula psicrometrica usada no
    fluxo manual (`thermal_indices.calcular_umidade_relativa` /
    `calcular_ponto_orvalho`). Diferente do fluxo manual (que tem um modo
    "medido"/"calculado" configuravel por campo), aqui a regra e sempre
    automatica: se ha sensor cadastrado para o campo, o valor medido vence;
    senao, deriva de tbs/tbu quando isso for possivel."""
    preparadas = dict(entradas)
    if "tbs" in preparadas and "tbu" in preparadas:
        try:
            tbs = float(preparadas["tbs"])
            tbu = float(preparadas["tbu"])
            if "ur" not in preparadas:
                preparadas["ur"] = round(ti.calcular_umidade_relativa(tbs, tbu, altitude), 1)
            if "tpo" not in preparadas:
                preparadas["tpo"] = round(ti.calcular_ponto_orvalho(tbs, tbu, altitude), 1)
        except (ti.EntradaInvalidaError, TypeError, ValueError):
            # Deixa a validacao normal do indice (mais abaixo, em
            # Temperatura.calcular_ict) reclamar do campo que realmente
            # faltar, com uma mensagem mais especifica do que esta funcao
            # conseguiria dar aqui.
            pass
    return preparadas


class ZonaService:
    def __init__(
        self,
        obter_zona: Callable[[int], dict | None],
        salvar_leitura: Callable,
        obter_configuracoes: Callable,
        ler_modbus: Callable = modbus_client.ler_valor,
        escrever_modbus: Callable = modbus_client.escrever_valor,
    ):
        self._obter_zona = obter_zona
        self._salvar_leitura = salvar_leitura
        self._obter_configuracoes = obter_configuracoes
        self._ler_modbus = ler_modbus
        self._escrever_modbus = escrever_modbus
        # Uma instancia de Resfriamento por zona: cada zona tem seu proprio
        # estado de intensidade/histerese, independente das demais.
        self._resfriadores: dict[int, Resfriamento] = {}
        self._lock = threading.Lock()

    def resfriador_da_zona(self, zona_id: int) -> Resfriamento:
        with self._lock:
            if zona_id not in self._resfriadores:
                self._resfriadores[zona_id] = Resfriamento()
            return self._resfriadores[zona_id]

    def ler_sensores(self, equipamentos: list[dict]) -> dict:
        """Le todos os sensores informados via Modbus e devolve a MEDIA das
        leituras por campo, quando ha mais de um sensor para o mesmo
        campo. Sensores que falharem sao ignorados na media (nao entram no
        calculo), mas ficam listados em 'sensores_com_falha' para
        diagnostico -- a leitura so falha por completo se NENHUM sensor de
        um campo necessario responder (ver `calcular`)."""
        leituras_por_campo: dict[str, list[float]] = {}
        falhas: list[str] = []
        for equipamento in equipamentos:
            if equipamento.get("tipo") != "sensor":
                continue
            campo = equipamento.get("campo_medido")
            if not campo:
                continue
            valor = self._ler_modbus(equipamento)
            if valor is None:
                falhas.append(equipamento["nome"])
                continue
            leituras_por_campo.setdefault(campo, []).append(valor)

        medias = {
            campo: round(sum(valores) / len(valores), 2)
            for campo, valores in leituras_por_campo.items()
        }
        return {"entradas": medias, "sensores_com_falha": falhas}

    def calcular(self, zona_id: int, logger=None) -> dict:
        zona = self._obter_zona(zona_id)
        if not zona:
            raise ZonaCalculoError(f"Zona {zona_id} não encontrada.")
        if not zona["ativa"]:
            raise ZonaCalculoError(f"A zona '{zona['nome']}' está desativada.")

        equipamentos = zona["equipamentos"]
        leitura = self.ler_sensores(equipamentos)

        try:
            altitude = float(self._obter_configuracoes().get("altitudeMetros") or 0)
        except Exception:
            altitude = 0.0
        entradas = _derivar_campos_calculaveis(leitura["entradas"], altitude)

        campos_necessarios = ti.CAMPOS_POR_INDICE[zona["indice"]]
        if not any(campo in entradas for campo in campos_necessarios):
            raise ZonaCalculoError(
                f"Nenhum sensor da zona '{zona['nome']}' respondeu com dados "
                f"suficientes para calcular o índice {zona['indice']}."
            )

        temperatura = Temperatura(zona["especie"], zona["indice"])
        valor, status = temperatura.calcular_ict(entradas)

        gravado = False
        try:
            gravado = self._salvar_leitura(
                zona["especie"],
                zona["indice"],
                valor,
                status,
                temperatura.entradas,
                zona_id=zona_id,
            )
        except Exception:
            if logger:
                logger.exception("Falha ao gravar histórico da zona %s", zona_id)

        resfriador = self.resfriador_da_zona(zona_id)
        resfriador.registrar_leitura(status)
        try:
            limite_umidade = float(
                self._obter_configuracoes().get("limiteUmidadeNebulizador") or 70
            )
        except Exception:
            limite_umidade = 70.0
        resfriador.aplicar_limite_umidade_nebulizador(entradas.get("ur"), limite_umidade)

        atuadores_com_falha = self._aplicar_atuadores(equipamentos, resfriador, logger)

        return {
            "zona_id": zona_id,
            "zona_nome": zona["nome"],
            "especie": zona["especie"],
            "indice": zona["indice"],
            "valor": valor,
            "status": status,
            "cor": ti.cor_do_status(status),
            "mensagem": ti.mensagem_do_status(status),
            "entradas": temperatura.entradas,
            "leitura_gravada": gravado,
            "sensores_com_falha": leitura["sensores_com_falha"],
            "equipamento": resfriador.estado(),
            "atuadores_com_falha": atuadores_com_falha,
        }

    def _aplicar_atuadores(
        self, equipamentos: list[dict], resfriador: Resfriamento, logger
    ) -> list[str]:
        estado = resfriador.estado()
        falhas: list[str] = []
        for equipamento in equipamentos:
            if equipamento.get("tipo") == "ventilador":
                ligar = estado["ventilador"]
            elif equipamento.get("tipo") == "nebulizador":
                ligar = estado["nebulizador"]
            else:
                continue

            sucesso = self._escrever_modbus(equipamento, ligar)
            if not sucesso:
                falhas.append(equipamento["nome"])
                if logger:
                    logger.warning(
                        "Falha ao acionar equipamento Modbus '%s'", equipamento["nome"]
                    )
        return falhas

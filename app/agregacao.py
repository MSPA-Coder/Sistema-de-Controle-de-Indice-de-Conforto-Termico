"""
agregacao.py
=============
Camada de agregacao temporal do historico de leituras.

Contexto (ver conversa com o usuario que motivou este modulo): o ciclo de
leitura roda a cada `intervaloLeituraSegundos`/`intervaloGravacaoMinutos`
(tipicamente 1 a 5 min) para dar resposta rapida ao controle automatico de
ventiladores/nebulizadores. Gravar CADA leitura bruta pra sempre funciona,
mas cresce rapido e nao e o formato que a literatura de conforto termico
usa pra reportar indices (ITU, IGNU etc. sao tradicionalmente reportados em
base horaria). Este modulo consolida a leitura bruta em duas camadas:

 1) 15 em 15 minutos -> `database.agregar_janela_15min` (media/minimo/
    maximo do indice e de cada variavel de entrada).
 2) 1 em 1 hora -> `database.consolidar_resumo_horario` (media horaria do
    indice, status classificado a partir dessa media, e percentual de
    leituras da hora em cada status).

As duas sao idempotentes e so processam janelas/horas FECHADAS (que ja
terminaram) e que ainda nao foram consolidadas -- rodar `executar()` de novo
sem leitura nova nao faz nada. Isso permite chamar `executar()` a cada ciclo
do coletor automatico (ver `coletor/controle.py`) sem se preocupar com
duplicar trabalho: o custo, quando nao ha janela pendente, e so a consulta
que checa se ha algo pendente.
"""

from __future__ import annotations

from . import database as db


def executar_para_zona(zona: dict, logger=None) -> dict:
    """Consolida todas as janelas de 15 min e horas pendentes de uma zona.
    `zona` e o dict retornado por `database.listar_zonas`/`obter_zona`
    (precisa ter `id`, `especie` e `indice`)."""
    zona_id = zona["id"]
    especie = zona["especie"]
    indice = zona["indice"]

    janelas_15min = 0
    for janela in db.janelas_15min_pendentes(zona_id, indice):
        try:
            if db.agregar_janela_15min(zona_id, especie, indice, janela):
                janelas_15min += 1
        except Exception:
            if logger:
                logger.exception("Falha ao agregar janela de 15min %s da zona %s", janela, zona_id)

    horas = 0
    for hora in db.horas_pendentes(zona_id, indice):
        try:
            if db.consolidar_resumo_horario(zona_id, especie, indice, hora):
                horas += 1
        except Exception:
            if logger:
                logger.exception("Falha ao consolidar resumo horario %s da zona %s", hora, zona_id)

    return {
        "zona_id": zona_id,
        "janelas_15min_consolidadas": janelas_15min,
        "horas_consolidadas": horas,
    }


def executar(logger=None) -> list[dict]:
    """Roda a consolidacao para todas as zonas cadastradas (ativas ou nao --
    uma zona desativada ainda pode ter leitura bruta pendente de
    consolidacao de quando estava ativa)."""
    resultados = []
    for zona in db.listar_zonas():
        resultados.append(executar_para_zona(zona, logger=logger))
    return resultados

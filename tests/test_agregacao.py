from __future__ import annotations

from app import agregacao
from app.coletor.controle import (
    INTERVALO_REPOUSO_SEM_AUTOMACAO_SEGUNDOS,
    GerenciadorControleZonas,
)


def test_consolidar_zona_processa_apenas_janelas_pendentes(monkeypatch):
    chamadas: list[tuple[str, str]] = []

    class BancoFalso:
        @staticmethod
        def janelas_15min_pendentes(zona_id, indice):
            assert (zona_id, indice) == (7, "ITU")
            return ["2026-08-16T10:00:00"]

        @staticmethod
        def agregar_janela_15min(zona_id, especie, indice, janela):
            chamadas.append(("15min", janela))
            return True

        @staticmethod
        def horas_pendentes(zona_id, indice):
            return ["2026-08-16T09:00:00"]

        @staticmethod
        def consolidar_resumo_horario(zona_id, especie, indice, hora):
            chamadas.append(("hora", hora))
            return True

    monkeypatch.setattr(agregacao, "db", BancoFalso)

    resultado = agregacao.executar_para_zona({"id": 7, "especie": "frangos", "indice": "ITU"})

    assert resultado == {
        "zona_id": 7,
        "janelas_15min_consolidadas": 1,
        "horas_consolidadas": 1,
    }
    assert chamadas == [("15min", "2026-08-16T10:00:00"), ("hora", "2026-08-16T09:00:00")]


def test_coletor_entra_em_reposo_sem_zona_automatica():
    gerenciador = GerenciadorControleZonas(zona_service=object())
    gerenciador._teve_zona_automatica_no_ultimo_ciclo = False

    intervalo = (
        gerenciador._intervalo_segundos()
        if gerenciador._teve_zona_automatica_no_ultimo_ciclo
        else INTERVALO_REPOUSO_SEM_AUTOMACAO_SEGUNDOS
    )

    assert intervalo == 60.0

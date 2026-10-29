"""A exclusão de zona não deve liberar outra operação enquanto há ciclo ativo."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.coletor import controle


def test_limpeza_de_zona_removida_aguarda_operacao_ativa(monkeypatch):
    limpezas = []

    class Servico:
        def limpar_historico_grafico(self, zona_id):
            limpezas.append(("grafico", zona_id))

        def limpar_resfriador(self, zona_id):
            limpezas.append(("resfriador", zona_id))

    gerenciador = controle.GerenciadorControleZonas(Servico())
    gerenciador._zonas_conhecidas = {1}
    zonas = []
    monkeypatch.setattr(controle.db, "listar_zonas", lambda: zonas)
    entrou, liberar = Event(), Event()

    def operacao():
        entrou.set()
        assert liberar.wait(10)

    with ThreadPoolExecutor(max_workers=1) as pool:
        futuro = pool.submit(gerenciador._executar_exclusivo, 1, operacao)
        assert entrou.wait(10)
        try:
            gerenciador._reconciliar_zonas_removidas()
            assert not limpezas
            with pytest.raises(controle.ZonaOcupadaError):
                gerenciador._executar_exclusivo(1, lambda: None)
        finally:
            liberar.set()
        futuro.result(timeout=10)
    zonas.append({"id": 1})  # Mesmo identificador aparece antes da limpeza pendente.
    gerenciador._reconciliar_zonas_removidas()
    assert limpezas == [("grafico", 1), ("resfriador", 1)]

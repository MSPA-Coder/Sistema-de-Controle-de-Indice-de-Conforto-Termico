import threading
import unittest

from app import database as db
from app.coletor.controle import (
    GerenciadorControleZonas,
    ZonaOcupadaError,
)
from app.zona_service import ZonaCalculoError
from tests.postgres_test_utils import TestCasePostgres


class _ZonaServiceFalso:
    def __init__(self):
        self.calculadas = []
        self.historicos_limpos = []
        self.resfriadores_limpos = []

    def calcular(self, zona_id, logger=None):
        self.calculadas.append(zona_id)
        return {
            "zona_id": zona_id,
            "zona_nome": f"Zona {zona_id}",
            "status": "Conforto",
            "valor": 70.0,
            "qualidade": "boa",
            "indice": "ITU",
            "entradas": {"tbs": 25.0, "tbu": 20.0},
        }

    def calcular_manual(self, zona_id, entradas, logger=None):
        return self.calcular(zona_id, logger)

    def limpar_historico_grafico(self, zona_id=None):
        self.historicos_limpos.append(zona_id)

    def limpar_resfriador(self, zona_id=None):
        self.resfriadores_limpos.append(zona_id)


class TestGerenciadorControleZonas(TestCasePostgres):
    def setUp(self):
        super().setUp()
        self.servico = _ZonaServiceFalso()
        self.gerenciador = GerenciadorControleZonas(self.servico)

    @staticmethod
    def _criar_zona(nome):
        return db.criar_zona({"nome": nome, "especie": "frangos", "indice": "ITU"})["id"]

    def test_ciclo_automatico_processa_somente_modo_automatico(self):
        zona_manual = self._criar_zona("Manual")
        zona_automatica = self._criar_zona("Automatica")
        db.salvar_controle_zona(zona_automatica, {"modo": "automatico"})

        resultados = self.gerenciador.executar_ciclo_automatico()

        self.assertEqual([zona_automatica], self.servico.calculadas)
        self.assertEqual([zona_automatica], [item["zona_id"] for item in resultados])
        self.assertNotIn(zona_manual, self.servico.calculadas)
        self.assertIsNotNone(db.obter_status_coletor()["ultimo_ciclo_em"])
        self.assertTrue(db.listar_eventos_operacao(zona_automatica))

    def test_falha_em_uma_zona_nao_interrompe_as_demais(self):
        zona_com_falha = self._criar_zona("Com falha")
        zona_saudavel = self._criar_zona("Saudável")
        for zona_id in (zona_com_falha, zona_saudavel):
            db.salvar_controle_zona(zona_id, {"modo": "automatico"})

        calcular_original = self.servico.calcular

        def calcular(zona_id, logger=None):
            if zona_id == zona_com_falha:
                raise ZonaCalculoError("sensor indisponível")
            return calcular_original(zona_id, logger)

        self.servico.calcular = calcular
        resultados = self.gerenciador.executar_ciclo_automatico()

        self.assertEqual(zona_com_falha, resultados[0]["zona_id"])
        self.assertEqual("sensor indisponível", resultados[0]["erro"])
        self.assertEqual(zona_saudavel, resultados[1]["zona_id"])
        self.assertIn(zona_saudavel, self.servico.calculadas)
        falhas = db.listar_eventos_operacao(zona_com_falha)
        self.assertEqual("falha", falhas[0]["acao"])
        self.assertEqual("sensor indisponível", falhas[0]["detalhes"]["erro"])

    def test_lock_impede_dois_ciclos_simultaneos_na_mesma_zona(self):
        zona_id = self._criar_zona("Concorrente")
        entrou = threading.Event()
        liberar = threading.Event()

        def calculo_bloqueado(zona, entradas, logger=None):
            entrou.set()
            liberar.wait(timeout=2)
            return {
                "zona_id": zona,
                "zona_nome": "Concorrente",
                "status": "Conforto",
                "valor": 70.0,
                "qualidade": "boa",
            }

        self.servico.calcular_manual = calculo_bloqueado
        thread = threading.Thread(
            target=lambda: self.gerenciador.calcular_manual(zona_id, {"tbs": 25})
        )
        thread.start()
        self.assertTrue(entrou.wait(timeout=2))
        try:
            with self.assertRaises(ZonaOcupadaError):
                self.gerenciador.calcular_manual(zona_id, {"tbs": 25})
            with self.assertRaises(ZonaOcupadaError):
                self.gerenciador.alterar_controle(zona_id, {"modo": "automatico"})
            self.assertEqual("manual", db.obter_controle_zona(zona_id)["modo"])
        finally:
            liberar.set()
            thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_reconciliacao_limpa_estado_de_zona_excluida_fora_do_processo(self):
        zona_a = self._criar_zona("A")
        zona_b = self._criar_zona("B")
        for zona_id in (zona_a, zona_b):
            db.salvar_controle_zona(zona_id, {"modo": "automatico"})

        # Primeiro ciclo: so estabelece a baseline de zonas conhecidas;
        # nenhuma zona "sumiu" ainda, entao nada e limpo.
        self.gerenciador.executar_ciclo_automatico()
        self.assertEqual([], self.servico.historicos_limpos)
        self.assertEqual([], self.servico.resfriadores_limpos)
        with self.gerenciador._locks_guard:
            self.assertIn(zona_a, self.gerenciador._locks)

        # Exclusao simulando o que a "outra parte" da aplicacao faz agora
        # (ver ict/administracao.py) -- direto no banco, sem passar
        # por este processo.
        db.excluir_zona(zona_a)
        self.gerenciador.executar_ciclo_automatico()

        self.assertEqual([zona_a], self.servico.historicos_limpos)
        self.assertEqual([zona_a], self.servico.resfriadores_limpos)
        with self.gerenciador._locks_guard:
            self.assertNotIn(zona_a, self.gerenciador._locks)
            self.assertIn(zona_b, self.gerenciador._locks)

    def test_ciclo_automatico_enfileira_notificacao_quando_configurado(self):
        from app import notificacoes

        zona_id = self._criar_zona("Notificada")
        db.salvar_controle_zona(zona_id, {"modo": "automatico"})
        db.salvar_configuracoes({"enviarEmails": True, "emailDestino": "produtor@fazenda.com.br"})

        enfileirados = []
        original = notificacoes.fila_notificacoes.enfileirar
        notificacoes.fila_notificacoes.enfileirar = lambda destino, conteudo, smtp_config: (
            enfileirados.append(destino)
        )
        try:
            resultados = self.gerenciador.executar_ciclo_automatico()
        finally:
            notificacoes.fila_notificacoes.enfileirar = original

        self.assertEqual(["produtor@fazenda.com.br"], enfileirados)
        self.assertTrue(resultados[0]["email"]["enfileirado"])

    def test_ciclo_automatico_nao_enfileira_notificacao_quando_desligado(self):
        from app import notificacoes

        zona_id = self._criar_zona("Sem alerta")
        db.salvar_controle_zona(zona_id, {"modo": "automatico"})
        db.salvar_configuracoes({"enviarEmails": False})

        enfileirados = []
        original = notificacoes.fila_notificacoes.enfileirar
        notificacoes.fila_notificacoes.enfileirar = lambda destino, conteudo, smtp_config: (
            enfileirados.append(destino)
        )
        try:
            resultados = self.gerenciador.executar_ciclo_automatico()
        finally:
            notificacoes.fila_notificacoes.enfileirar = original

        self.assertEqual([], enfileirados)
        self.assertNotIn("email", resultados[0])


if __name__ == "__main__":
    unittest.main()

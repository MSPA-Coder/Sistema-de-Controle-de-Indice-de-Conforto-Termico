# -*- coding: utf-8 -*-
"""Testes da camada de agregacao (15min/hora) descrita em agregacao.py."""

import datetime
import os
import tempfile
import unittest

from app import agregacao
from app import database as db


def _inserir_leitura_bruta(zona_id, valor, criado_em, status="Conforto", entradas=None):
    entradas = entradas or {"tbs": 27.0, "tbu": 19.0}
    with db._conexao() as conn:
        conn.execute(
            """
            INSERT INTO leituras (especie, indice, valor, status, entradas, criado_em, zona_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("frangos", "ITU", valor, status, __import__("json").dumps(entradas), criado_em, zona_id),
        )


class TestAgregacao15minEHora(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()
        self.zona = db.criar_zona(
            {"nome": "Aviario Teste", "especie": "frangos", "indice": "ITU", "ativa": True}
        )

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _agora_menos(self, **kwargs):
        return (
            (datetime.datetime.now() - datetime.timedelta(**kwargs))
            .replace(microsecond=0)
            .isoformat(timespec="seconds")
        )

    def test_janela_15min_agrega_media_min_max(self):
        base = datetime.datetime.now() - datetime.timedelta(hours=2)
        base = base.replace(minute=0, second=0, microsecond=0)
        for i, valor in enumerate([70.0, 72.0, 74.0]):
            ts = (base + datetime.timedelta(minutes=i * 4)).isoformat(timespec="seconds")
            _inserir_leitura_bruta(self.zona["id"], valor, ts)

        resultado = agregacao.executar_para_zona(self.zona)
        self.assertEqual(1, resultado["janelas_15min_consolidadas"])

        agregados = db.obter_agregados_15min(self.zona["id"])
        self.assertEqual(1, len(agregados))
        self.assertEqual(3, agregados[0]["amostras"])
        self.assertAlmostEqual(72.0, agregados[0]["valor_medio"])
        self.assertEqual(70.0, agregados[0]["valor_minimo"])
        self.assertEqual(74.0, agregados[0]["valor_maximo"])
        self.assertEqual(27.0, agregados[0]["entradas_medias"]["tbs"])

    def test_janela_em_andamento_nao_e_consolidada(self):
        # Leitura de "agora" cai numa janela de 15min ainda ABERTA -- nao
        # deve ser consolidada ate a janela fechar.
        # Use o instante atual: subtrair alguns segundos torna o teste
        # intermitente quando ele começa logo após a virada de um quarto de
        # hora, pois a leitura cai corretamente na janela recém-fechada.
        _inserir_leitura_bruta(self.zona["id"], 70.0, self._agora_menos(seconds=0))
        resultado = agregacao.executar_para_zona(self.zona)
        self.assertEqual(0, resultado["janelas_15min_consolidadas"])
        self.assertEqual([], db.obter_agregados_15min(self.zona["id"]))

    def test_resumo_horario_classifica_pela_media_e_calcula_percentuais(self):
        base = (datetime.datetime.now() - datetime.timedelta(hours=3)).replace(
            minute=0, second=0, microsecond=0
        )
        # 3 leituras em conforto (baixo) + 1 leitura bem alta (emergencia),
        # todas marcadas com o status calculado no momento da leitura.
        valores_e_status = [
            (65.0, "Conforto"),
            (66.0, "Conforto"),
            (67.0, "Conforto"),
            (95.0, "Emergência"),
        ]
        for i, (valor, status) in enumerate(valores_e_status):
            ts = (base + datetime.timedelta(minutes=i * 10)).isoformat(timespec="seconds")
            _inserir_leitura_bruta(self.zona["id"], valor, ts, status=status)

        agregacao.executar_para_zona(self.zona)
        resumos = db.obter_resumos_horarios(self.zona["id"])
        self.assertEqual(1, len(resumos))
        resumo = resumos[0]
        self.assertEqual(4, resumo["amostras"])
        self.assertAlmostEqual((65 + 66 + 67 + 95) / 4, resumo["valor_medio"], places=2)
        # 3 de 4 leituras (75%) vieram marcadas como "Conforto".
        self.assertEqual(75.0, resumo["pct_conforto"])
        self.assertEqual(25.0, resumo["pct_emergencia"])
        # Status da MEDIA (73.25) e calculado de novo a partir do valor
        # medio -- nao e a moda dos status individuais.
        from app import thermal_indices as ti
        esperado = ti.classificar_status(resumo["valor_medio"], "frangos", "ITU")
        self.assertEqual(esperado, resumo["status_da_media"])

    def test_execucao_e_idempotente(self):
        base = (datetime.datetime.now() - datetime.timedelta(hours=2)).replace(
            minute=0, second=0, microsecond=0
        )
        _inserir_leitura_bruta(self.zona["id"], 70.0, base.isoformat(timespec="seconds"))

        primeira = agregacao.executar_para_zona(self.zona)
        segunda = agregacao.executar_para_zona(self.zona)

        self.assertEqual(1, primeira["janelas_15min_consolidadas"])
        self.assertEqual(0, segunda["janelas_15min_consolidadas"])
        self.assertEqual(1, len(db.obter_agregados_15min(self.zona["id"])))
        self.assertEqual(1, len(db.obter_resumos_horarios(self.zona["id"])))

    def test_filtro_por_periodo_no_resumo_horario(self):
        antiga = (datetime.datetime.now() - datetime.timedelta(days=10)).replace(
            minute=0, second=0, microsecond=0
        )
        recente = (datetime.datetime.now() - datetime.timedelta(hours=2)).replace(
            minute=0, second=0, microsecond=0
        )
        _inserir_leitura_bruta(self.zona["id"], 70.0, antiga.isoformat(timespec="seconds"))
        _inserir_leitura_bruta(self.zona["id"], 71.0, recente.isoformat(timespec="seconds"))
        agregacao.executar_para_zona(self.zona)

        hoje = datetime.date.today().isoformat()
        filtrados = db.obter_resumos_horarios(self.zona["id"], data_inicio=hoje, data_fim=hoje)
        self.assertEqual(1, len(filtrados))

    def test_limpar_historico_remove_tabelas_agregadas(self):
        base = (datetime.datetime.now() - datetime.timedelta(hours=2)).replace(
            minute=0, second=0, microsecond=0
        )
        _inserir_leitura_bruta(self.zona["id"], 70.0, base.isoformat(timespec="seconds"))
        agregacao.executar_para_zona(self.zona)
        self.assertTrue(db.obter_agregados_15min(self.zona["id"]))

        db.limpar_historico()
        self.assertEqual([], db.obter_agregados_15min(self.zona["id"]))
        self.assertEqual([], db.obter_resumos_horarios(self.zona["id"]))


if __name__ == "__main__":
    unittest.main()

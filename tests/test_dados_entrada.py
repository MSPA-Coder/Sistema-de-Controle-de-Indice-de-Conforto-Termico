# -*- coding: utf-8 -*-
import datetime
import os
import random
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from conforto_termico import database as db
from conforto_termico import dados_entrada_db as dados_db
from conforto_termico import gerador_dados as gerador
from conforto_termico.app_factory import AppConfig, criar_app
from conforto_termico.dados_entrada_cidades import referencias_publicas


class TestDadosEntrada(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_original = db.DB_PATH
        self.dados_db_original = dados_db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        dados_db.DB_PATH = os.path.join(self.tempdir.name, "dados_entrada.db")
        db.iniciar_banco()
        dados_db.iniciar_banco()
        self.zona = db.criar_zona(
            {"nome": "Estábulo teste", "especie": "bovinos", "indice": "ITU", "ativa": True}
        )

    def tearDown(self):
        db.DB_PATH = self.db_original
        dados_db.DB_PATH = self.dados_db_original
        self.tempdir.cleanup()

    def _configurar_zona(self):
        return dados_db.salvar_configuracoes_zonas(
            [
                {
                    "zona_id": self.zona["id"],
                    "cidade_codigo_ibge": "4104907",
                    "latitude": -23.55,
                    "longitude": -46.63,
                    "fuso_horario": "UTC",
                    "altitude_m": 760,
                    "peso_medio_kg": 620,
                    "area_util_m2": 600,
                    "densidade_categoria": "media",
                    "producao_leite_kg_dia": 28,
                    "ordenhas_dia": 2,
                }
            ],
            db.listar_zonas(),
        )

    @staticmethod
    def _clima_falso(url):
        parametros = parse_qs(urlparse(url).query)
        inicio = datetime.date.fromisoformat(parametros["start_date"][0])
        fim = datetime.date.fromisoformat(parametros["end_date"][0])
        atual = datetime.datetime.combine(inicio, datetime.time.min)
        limite = datetime.datetime.combine(fim + datetime.timedelta(days=1), datetime.time.min)
        tempos = []
        while atual < limite:
            tempos.append(atual.isoformat(timespec="minutes"))
            atual += datetime.timedelta(hours=1)
        total = len(tempos)
        temperatura = [24 + (i % 24) * 0.1 for i in range(total)]
        return {
            "hourly": {
                "time": tempos,
                "temperature_2m": temperatura,
                "relative_humidity_2m": [70.0] * total,
                "wind_speed_10m": [1.5] * total,
                "precipitation": [0.6] * total,
                "surface_pressure": [930.0] * total,
                "shortwave_radiation": [400.0] * total,
                "cloud_cover": [35.0] * total,
            }
        }

    def test_gera_intervalo_de_cinco_minutos_com_origem_rastreavel(self):
        self._configurar_zona()
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso):
            resultado = gerador.gerar(
                {
                    "dias": 1,
                    "intervalo_minutos": 5,
                    "data_final": "2024-01-10",
                    "semente": 123,
                },
                db.listar_zonas(),
            )
        self.assertEqual(288, resultado["total_medicoes"])
        execucao = dados_db.obter_execucao(resultado["execucao_id"])
        self.assertEqual("concluida", execucao["status"])
        colunas, linhas = dados_db.obter_medicoes_csv(resultado["execucao_id"])
        self.assertEqual(288, len(linhas))
        primeira = dict(zip(colunas, linhas[0]))
        segunda = dict(zip(colunas, linhas[1]))
        self.assertLessEqual(primeira["ponto_orvalho_c"], primeira["tbs_externa_c"])
        self.assertEqual("reanálise_horária", primeira["indicador_qualidade"])
        self.assertEqual("reanálise_interpolada", segunda["indicador_qualidade"])
        self.assertEqual(40, primeira["animais_em_pe"] + primeira["animais_deitados"])
        self.assertEqual(600, primeira["area_util_m2"])
        self.assertEqual("media", primeira["densidade_categoria"])
        self.assertAlmostEqual(40 / 600, primeira["densidade_animais_m2"], places=6)
        self.assertAlmostEqual(0.05, segunda["precipitacao_mm"], places=5)

    def test_quantidade_e_calculada_por_area_peso_especie_e_categoria(self):
        base = {
            "zona_id": self.zona["id"], "cidade_codigo_ibge": "4104907",
            "latitude": -23.55, "longitude": -46.63, "fuso_horario": "UTC",
            "altitude_m": 760, "peso_medio_kg": 620, "area_util_m2": 600,
            "producao_leite_kg_dia": 28, "ordenhas_dia": 2,
            "quantidade_animais": 999999,
        }
        quantidades = []
        configs = []
        for categoria in (
            "abaixo_media", "media", "acima_media", "muito_acima_media"
        ):
            config = dados_db.salvar_configuracoes_zonas(
                [{**base, "densidade_categoria": categoria}], [self.zona]
            )[0]
            quantidades.append(config["quantidade_animais"])
            configs.append(dict(config))
        self.assertEqual([30, 40, 47, 50], quantidades)
        self.assertEqual(sorted(quantidades), quantidades)

        instante = datetime.datetime(2024, 1, 10, 12, tzinfo=datetime.timezone.utc)
        calor_baixo = gerador.simular_animais(
            configs[0], instante, 25, 70, 5, random.Random(123)
        )["calor_sensivel_animais_w"]
        calor_muito_alto = gerador.simular_animais(
            configs[-1], instante, 25, 70, 5, random.Random(123)
        )["calor_sensivel_animais_w"]
        self.assertGreater(calor_muito_alto, calor_baixo)

    def test_recusa_periodo_recente_demais_para_consolidacao_era5(self):
        recente = datetime.date.today() - datetime.timedelta(days=7)
        with self.assertRaisesRegex(gerador.GeracaoDadosError, "atraso de consolidação"):
            gerador.validar_parametros(
                {"dias": 1, "intervalo_minutos": 60, "data_final": recente.isoformat()},
                1,
            )

    def test_recusa_lacuna_em_vez_de_repetir_ultimo_valor(self):
        tempos = [
            datetime.datetime(2024, 1, 1, hora, tzinfo=datetime.timezone.utc)
            for hora in range(3)
        ]
        with self.assertRaisesRegex(gerador.GeracaoDadosError, "lacuna"):
            gerador._interpolar(
                tempos,
                [20.0, None, None],
                datetime.datetime(2024, 1, 1, 1, tzinfo=datetime.timezone.utc),
            )

    def test_cache_incompleto_e_descartado_e_fonte_e_consultada_novamente(self):
        self._configurar_zona()
        inicio = datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
        fim = inicio + datetime.timedelta(days=1)
        resposta_incompleta = self._clima_falso(
            "https://exemplo.test?start_date=2024-01-09&end_date=2024-01-12"
        )
        for serie in resposta_incompleta["hourly"].values():
            if isinstance(serie, list) and serie is not resposta_incompleta["hourly"]["time"]:
                serie[24:49] = [None] * 25
        chave = gerador._chave_cache(-23.55, -46.63, "2024-01-09", "2024-01-12")
        dados_db.salvar_cache_clima(chave, resposta_incompleta, gerador.FONTE_CLIMA)
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso) as baixar:
            bruto = gerador.obter_clima_horario(-23.55, -46.63, inicio, fim)
        self.assertTrue(baixar.called)
        completa, _ = gerador._avaliar_cobertura_clima(bruto, inicio, fim)
        self.assertTrue(completa)

    def test_recusa_zona_sem_parametros_reais_e_zootecnicos(self):
        with self.assertRaisesRegex(gerador.GeracaoDadosError, "Complete localização"):
            gerador.gerar(
                {"dias": 1, "intervalo_minutos": 60, "data_final": "2024-01-10"},
                db.listar_zonas(),
            )

    def test_gera_somente_para_zonas_ativas(self):
        self._configurar_zona()
        db.criar_zona({
            "nome": "Zona inativa", "especie": "suinos",
            "indice": "ITU", "ativa": False,
        })
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso):
            resultado = gerador.gerar(
                {"dias": 1, "intervalo_minutos": 60, "data_final": "2024-01-10"},
                db.listar_zonas(),
            )
        self.assertEqual(1, resultado["total_zonas"])
        self.assertEqual(24, resultado["total_medicoes"])

    def test_parametros_e_cidades_respeitam_a_especie(self):
        referencias = referencias_publicas()
        self.assertEqual(5, len(referencias["cidades_por_especie"]["frangos"]))
        self.assertEqual(2.5, referencias["peso_medio_estimado_kg"]["frangos"])
        self.assertEqual(4, len(referencias["lotacao"]["categorias"]))
        suinos = db.criar_zona({
            "nome": "Suinocultura", "especie": "suinos",
            "indice": "ITU", "ativa": True,
        })
        base = {
            "zona_id": suinos["id"], "cidade_codigo_ibge": "4127700",
            "latitude": -24.71361, "longitude": -53.74306,
            "fuso_horario": "America/Sao_Paulo", "altitude_m": 562,
            "peso_medio_kg": 100, "area_util_m2": 325,
            "densidade_categoria": "media",
            "producao_leite_kg_dia": 0, "ordenhas_dia": 0,
        }
        salvas = dados_db.salvar_configuracoes_zonas([base], [suinos])
        self.assertEqual(0, salvas[0]["ordenhas_dia"])
        with self.assertRaisesRegex(
            dados_db.ConfiguracaoDadosEntradaError, "só se aplicam"
        ):
            dados_db.salvar_configuracoes_zonas(
                [{**base, "ordenhas_dia": 1}], [suinos]
            )

    def test_dashboard_consulta_mas_nao_registra_rotas_de_mutacao(self):
        app = criar_app("dashboard", AppConfig.from_env("dashboard"))
        cliente = app.test_client()
        self.assertEqual(200, cliente.get("/api/dados-entrada/execucoes").status_code)
        self.assertEqual(200, cliente.get("/api/dados-entrada/referencias").status_code)
        self.assertEqual(404, cliente.post("/api/dados-entrada/gerar", json={}).status_code)

    def test_copia_geracao_para_historico_de_forma_idempotente(self):
        self._configurar_zona()
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso):
            resultado = gerador.gerar(
                {"dias": 1, "intervalo_minutos": 60, "data_final": "2024-01-10"},
                db.listar_zonas(),
            )
        self.assertEqual(0, db.contar_leituras())
        primeira = dados_db.copiar_medicoes_para_historico(resultado["execucao_id"])
        self.assertEqual(24, primeira["novas_copiadas"])
        self.assertEqual(24, db.contar_leituras())
        segunda = dados_db.copiar_medicoes_para_historico(resultado["execucao_id"])
        self.assertEqual(0, segunda["novas_copiadas"])
        self.assertEqual(24, segunda["total_copiado"])
        self.assertEqual(24, db.contar_leituras())

    def test_valida_fuso_horario(self):
        dados = {
            "zona_id": self.zona["id"], "cidade_codigo_ibge": "4104907",
            "latitude": 0, "longitude": 0,
            "fuso_horario": "Fuso/Inexistente", "altitude_m": 0,
            "peso_medio_kg": 500, "area_util_m2": 15,
            "densidade_categoria": "media",
            "producao_leite_kg_dia": 0, "ordenhas_dia": 0,
        }
        with self.assertRaises(dados_db.ConfiguracaoDadosEntradaError):
            dados_db.salvar_configuracoes_zonas([dados], db.listar_zonas())


if __name__ == "__main__":
    unittest.main()

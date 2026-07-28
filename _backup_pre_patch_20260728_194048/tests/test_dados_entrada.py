# -*- coding: utf-8 -*-
import datetime
import json
import os
import random
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app import database as db
from app import dados_entrada_db as dados_db
from app import gerador_dados as gerador
from app.app_factory import criar_app_ict
from app.dados_entrada_cidades import referencias_publicas
from tests.auth_test_utils import cliente_autenticado


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

    def test_recusa_fonte_com_lacuna_no_periodo_solicitado(self):
        inicio = datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
        fim = inicio + datetime.timedelta(days=1)
        resposta = self._clima_falso(
            "https://exemplo.test?start_date=2024-01-09&end_date=2024-01-12"
        )
        resposta["hourly"]["temperature_2m"][25] = None

        with patch.object(gerador, "_baixar_json", return_value=resposta):
            with self.assertRaisesRegex(
                gerador.GeracaoDadosError,
                "não consolidou todo o período",
            ):
                gerador.obter_clima_horario(-23.55, -46.63, inicio, fim)

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
            resultado = gerador.obter_clima_horario(-23.55, -46.63, inicio, fim)
        self.assertTrue(baixar.called)
        self.assertIn(inicio, resultado.tempos)
        self.assertIn(fim, resultado.tempos)
        self.assertEqual(len(resultado.tempos), len(resultado.series["tbs"]))
        self.assertNotIn(None, resultado.series["tbs"])

    def test_cache_malformado_e_descartado_sem_lancar_excecao(self):
        self._configurar_zona()
        inicio = datetime.datetime(2024, 1, 10, tzinfo=datetime.timezone.utc)
        fim = inicio + datetime.timedelta(days=1)
        chave = gerador._chave_cache(-23.55, -46.63, "2024-01-09", "2024-01-12")
        # Uma entrada sem "hourly" espelha um cache corrompido: `_serie_clima`
        # levanta KeyError ao tentar parsea-la. O caminho de cache de
        # `obter_clima_horario` precisa tratar isso como cobertura incompleta
        # -- sem deixar a exceção escapar -- e buscar da fonte normalmente.
        dados_db.salvar_cache_clima(chave, {"nao_e_hourly": True}, gerador.FONTE_CLIMA)
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso) as baixar:
            resultado = gerador.obter_clima_horario(-23.55, -46.63, inicio, fim)
        self.assertTrue(baixar.called)
        self.assertIn("hourly", resultado.bruto)
        # O cache malformado foi substituído pela resposta válida recém-baixada.
        self.assertIn("hourly", dados_db.obter_cache_clima(chave))

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

    def test_ict_registra_leitura_e_mutacao_de_dados_de_entrada(self):
        app = criar_app_ict()
        cliente = cliente_autenticado(app)
        self.assertEqual(200, cliente.get("/api/dados-entrada/execucoes").status_code)
        self.assertEqual(200, cliente.get("/api/dados-entrada/referencias").status_code)
        self.assertNotEqual(404, cliente.post("/api/dados-entrada/gerar", json={}).status_code)

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

    def test_sessao_geracao_permite_multiplos_lotes_na_mesma_conexao(self):
        execucao_id = dados_db.criar_execucao(
            data_inicio="2024-01-10", data_fim="2024-01-10", dias=1,
            intervalo_minutos=60, semente=1, total_zonas=1,
            fonte_clima=gerador.FONTE_CLIMA,
        )
        origem_json = gerador._metadados_origem_json()

        def _medicao(hora):
            return {
                "execucao_id": execucao_id, "zona_id": self.zona["id"],
                "zona_nome": self.zona["nome"], "especie": "bovinos", "indice": "ITU",
                "timestamp_utc": f"2024-01-10T{hora:02d}:00",
                "timestamp_local": f"2024-01-10T{hora:02d}:00",
                "fuso_horario": "UTC", "tbs_externa_c": 25.0, "ur_externa_pct": 70.0,
                "ponto_orvalho_c": 19.0, "tbu_c": 20.0, "velocidade_vento_ms": 1.0,
                "precipitacao_mm": 0.0, "pressao_hpa": 930.0, "radiacao_w_m2": 0.0,
                "nebulosidade_pct": 0.0, "valor_indice": 73.0, "status_termico": "Conforto",
                "area_util_m2": 600.0, "densidade_categoria": "media",
                "densidade_animais_m2": 0.06, "quantidade_animais": 40,
                "atividade_predominante": "repouso", "alimentacao_kg": 0.0,
                "consumo_agua_l": 0.0, "animais_em_pe": 10, "animais_deitados": 30,
                "animais_em_ordenha": 0, "calor_sensivel_animais_w": 0.0,
                "calor_latente_animais_w": 0.0, "vapor_agua_animais_kg_h": 0.0,
                "origem_variaveis": origem_json, "indicador_qualidade": "reanálise_horária",
                "entradas_indice": {"tbs": 25.0, "tbu": 20.0}, "simulation_seed": 1,
            }

        # Duas chamadas a `inserir_medicoes` na MESMA sessao (mesma conexao
        # reaproveitada) devem persistir tudo, cada uma com seu proprio commit.
        with dados_db.sessao_geracao() as sessao:
            sessao.inserir_medicoes([_medicao(0), _medicao(1)])
            sessao.inserir_medicoes([_medicao(2)])
        dados_db.concluir_execucao(execucao_id, 3)

        colunas, linhas = dados_db.obter_medicoes_csv(execucao_id)
        self.assertEqual(3, len(linhas))
        indice_origem = colunas.index("origem_variaveis")
        # A string de origem gravada precisa continuar sendo um JSON valido e
        # identico ao dict original, mesmo tendo sido passada ja serializada.
        self.assertEqual(json.loads(origem_json), json.loads(linhas[0][indice_origem]))

    def test_geracao_grande_atravessa_multiplos_lotes_reaproveitando_conexao(self):
        self._configurar_zona()
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso):
            resultado = gerador.gerar(
                {
                    "dias": 2, "intervalo_minutos": 1, "data_final": "2024-01-10",
                    "semente": 7,
                },
                db.listar_zonas(),
            )
        esperado = 2 * 24 * 60
        # Garante que este teste realmente atravessa mais de um lote (a
        # motivacao de `sessao_geracao`), em vez de caber em um so.
        self.assertGreater(esperado, gerador.TAMANHO_LOTE_INSERCAO)
        self.assertEqual(esperado, resultado["total_medicoes"])
        self.assertEqual("concluida", dados_db.obter_execucao(resultado["execucao_id"])["status"])
        _colunas, linhas = dados_db.obter_medicoes_csv(resultado["execucao_id"])
        self.assertEqual(esperado, len(linhas))

    def test_origem_variaveis_e_identica_e_valida_em_toda_a_execucao(self):
        self._configurar_zona()
        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso):
            resultado = gerador.gerar(
                {"dias": 1, "intervalo_minutos": 30, "data_final": "2024-01-10"},
                db.listar_zonas(),
            )
        colunas, linhas = dados_db.obter_medicoes_csv(resultado["execucao_id"])
        indice_origem = colunas.index("origem_variaveis")
        origens = {linha[indice_origem] for linha in linhas}
        # Mesma string em toda a execucao: prova que a serializacao unica
        # (`_metadados_origem_json`) nao introduziu variacao entre linhas.
        self.assertEqual(1, len(origens))
        origem = json.loads(next(iter(origens)))
        self.assertEqual(gerador.FONTE_CLIMA, origem["tbs_externa_c"])
        self.assertIn("Stull", origem["tbu_c"])

    def test_falha_em_zona_seguinte_limpa_medicoes_ja_gravadas_de_outra_zona(self):
        self._configurar_zona()
        outra = db.criar_zona({
            "nome": "Aviário teste", "especie": "frangos", "indice": "ITU", "ativa": True,
        })
        dados_db.salvar_configuracoes_zonas(
            [{
                "zona_id": outra["id"], "cidade_codigo_ibge": "3204559",
                "latitude": -20.02745, "longitude": -40.74336, "fuso_horario": "UTC",
                "altitude_m": 713, "peso_medio_kg": 2.5, "area_util_m2": 200,
                "densidade_categoria": "media",
                "producao_leite_kg_dia": 0, "ordenhas_dia": 0,
            }],
            db.listar_zonas(),
        )

        original = gerador._clima_no_instante
        contador = {"chamadas": 0}

        def _falha_a_partir_da_segunda_zona(tempos, series, alvo, intervalo_minutos):
            contador["chamadas"] += 1
            # A primeira zona (24 pontos, 1 dia a cada 60 min) e gerada e
            # confirmada normalmente; a falha simulada so comeca no primeiro
            # ponto da segunda zona, apos a primeira ja estar commitada.
            if contador["chamadas"] > 24:
                raise RuntimeError("falha simulada no meio da geração")
            return original(tempos, series, alvo, intervalo_minutos)

        with patch.object(gerador, "_baixar_json", side_effect=self._clima_falso), \
                patch.object(gerador, "_clima_no_instante", side_effect=_falha_a_partir_da_segunda_zona):
            with self.assertRaises(RuntimeError):
                gerador.gerar(
                    {"dias": 1, "intervalo_minutos": 60, "data_final": "2024-01-10"},
                    db.listar_zonas(),
                )

        self.assertGreater(contador["chamadas"], 24)
        # A zona que ja tinha sido commitada antes da falha nao pode
        # permanecer gravada: `falhar_execucao` precisa limpar tudo, mesmo
        # com a conexao de insercao sendo reaproveitada entre zonas.
        _colunas, linhas = dados_db.obter_medicoes_csv()
        self.assertEqual(0, len(linhas))
        execucoes = dados_db.listar_execucoes()
        self.assertEqual(1, len(execucoes))
        self.assertEqual("falhou", execucoes[0]["status"])


if __name__ == "__main__":
    unittest.main()

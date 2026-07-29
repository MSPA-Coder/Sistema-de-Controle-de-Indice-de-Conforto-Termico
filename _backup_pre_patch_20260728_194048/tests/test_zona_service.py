"""
test_zona_service.py
=====================
Testa ZonaService (leitura de sensores Modbus com MEDIA quando ha mais de
um sensor por campo, calculo do indice, gravacao no historico com zona_id,
e acionamento dos atuadores) usando funcoes de leitura/escrita Modbus
falsas -- sem depender de hardware real.
"""

import os
import tempfile
import unittest

from app import database as db
from app.zona_service import ZonaCalculoError, ZonaService


def _ignorar_estado_equipamentos(*args):
    pass


class TestZonaService(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

        self.leituras_simuladas: dict[str, float | None] = {}
        self.escritas: list[tuple[str, bool]] = []

        def ler_mock(equipamento):
            return self.leituras_simuladas.get(equipamento["nome"])

        def escrever_mock(equipamento, ligar):
            self.escritas.append((equipamento["nome"], ligar))
            return True

        self.servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            salvar_estado_equipamentos=_ignorar_estado_equipamentos,
            obter_controle_zona=db.obter_controle_zona,
            ler_modbus_real=ler_mock,
            escrever_modbus_real=escrever_mock,
        )

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _criar_zona_com_sensores(self, especie="frangos", indice="ITU"):
        zona = db.criar_zona({"nome": "Zona Teste", "especie": especie, "indice": indice})
        return zona

    def _equipamento_sensor(self, zona_id, nome, campo, **sobrescritas):
        base = {
            "tipo": "sensor",
            "nome": nome,
            "modo_conexao": "tcp",
            "host": "10.0.0.1",
            "tipo_registrador": "input",
            "endereco_registrador": 1,
            "campo_medido": campo,
        }
        base.update(sobrescritas)
        return db.criar_equipamento(zona_id, base)

    def test_media_de_dois_sensores_do_mesmo_campo(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBS-B", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 30.0, "TBS-B": 34.0, "TBU-A": 22.0}

        resultado = self.servico.calcular(zona["id"])

        self.assertEqual(32.0, resultado["entradas"]["tbs"])
        self.assertEqual([], resultado["sensores_com_falha"])

    def test_sensor_unico_usa_o_proprio_valor(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 28.0, "TBU-A": 20.0}

        resultado = self.servico.calcular(zona["id"])
        self.assertEqual(28.0, resultado["entradas"]["tbs"])

    def test_sensor_com_falha_e_ignorado_na_media_mas_reportado(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-OK", "tbs")
        self._equipamento_sensor(zona["id"], "TBS-COM-DEFEITO", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-OK": 28.0, "TBU-A": 20.0}  # TBS-COM-DEFEITO ausente -> None

        resultado = self.servico.calcular(zona["id"])

        self.assertEqual(28.0, resultado["entradas"]["tbs"])
        self.assertIn("TBS-COM-DEFEITO", resultado["sensores_com_falha"])

    def test_nenhum_sensor_responde_leva_a_erro_claro(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {}  # nada responde

        with self.assertRaises(ZonaCalculoError):
            self.servico.calcular(zona["id"])

    def test_zona_inexistente_leva_a_erro_claro(self):
        with self.assertRaises(ZonaCalculoError):
            self.servico.calcular(99999)

    def test_zona_desativada_leva_a_erro_claro(self):
        zona = self._criar_zona_com_sensores()
        db.atualizar_zona(zona["id"], {**zona, "ativa": False})
        with self.assertRaises(ZonaCalculoError):
            self.servico.calcular(zona["id"])

    def test_grava_historico_com_zona_id(self):
        zona = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 25.0, "TBU-A": 20.0}

        self.servico.calcular(zona["id"])

        historico = db.obter_historico_por_zona(zona["id"])
        self.assertEqual(1, len(historico))
        self.assertEqual(zona["id"], historico[0]["zona_id"])

    def test_itu_inclui_campos_derivados_no_historico_para_grafico(self):
        zona = self._criar_zona_com_sensores(indice="ITU")
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self.leituras_simuladas = {"TBS-A": 25.0, "TBU-A": 20.0}

        resultado = self.servico.calcular(zona["id"])

        self.assertIn("ur", resultado["entradas"])
        self.assertIn("tpo", resultado["entradas"])
        historico = db.obter_historico_por_zona(zona["id"])
        self.assertIn("ur", historico[0]["entradas"])
        self.assertIn("tpo", historico[0]["entradas"])

    def test_calculo_manual_aceita_umidade_como_texto_no_limite_do_nebulizador(self):
        zona = self._criar_zona_com_sensores(indice="ITU")
        db.criar_equipamento(zona["id"], {
            "tipo": "nebulizador", "nome": "NEB-1", "modo_conexao": "tcp", "host": "10.0.0.3",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })

        resultado = self.servico.calcular_manual(
            zona["id"], {"tbs": "45", "tbu": "25", "ur": "55,5"}
        )

        self.assertEqual("Emergência", resultado["status"])
        self.assertTrue(resultado["equipamento"]["nebulizador"])

    def test_duas_zonas_tem_estado_de_resfriamento_independente(self):
        zona_quente = self._criar_zona_com_sensores()
        zona_fria = self._criar_zona_com_sensores()
        self._equipamento_sensor(zona_quente["id"], "TBS-QUENTE", "tbs")
        self._equipamento_sensor(zona_quente["id"], "TBU-QUENTE", "tbu")
        self._equipamento_sensor(zona_fria["id"], "TBS-FRIA", "tbs")
        self._equipamento_sensor(zona_fria["id"], "TBU-FRIA", "tbu")

        self.leituras_simuladas = {
            "TBS-QUENTE": 38.0, "TBU-QUENTE": 30.0,  # deve dar Perigo/Emergencia
            "TBS-FRIA": 20.0, "TBU-FRIA": 18.0,  # deve dar Conforto
        }

        quente = self.servico.calcular(zona_quente["id"])
        fria = self.servico.calcular(zona_fria["id"])

        self.assertNotEqual(quente["status"], "Conforto")
        self.assertEqual("Conforto", fria["status"])
        self.assertTrue(quente["equipamento"]["ativo"])
        self.assertFalse(fria["equipamento"]["ativo"])

    def test_atuadores_sao_acionados_conforme_status(self):
        zona = self._criar_zona_com_sensores()
        db.salvar_configuracoes({"habilitarEquipamentos": True})
        db.salvar_controle_zona(
            zona["id"], {"modo": "manual", "acionamento_habilitado": True}
        )
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        db.criar_equipamento(zona["id"], {
            "tipo": "ventilador", "nome": "VENT-1", "modo_conexao": "tcp", "host": "10.0.0.2",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })
        db.criar_equipamento(zona["id"], {
            "tipo": "nebulizador", "nome": "NEB-1", "modo_conexao": "tcp", "host": "10.0.0.3",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })
        self.leituras_simuladas = {"TBS-A": 38.0, "TBU-A": 30.0}

        self.servico.calcular(zona["id"])

        nomes_acionados = {nome for nome, ligar in self.escritas if ligar}
        self.assertIn("VENT-1", nomes_acionados)
        self.assertIn("NEB-1", nomes_acionados)

    def test_deriva_umidade_relativa_de_tbs_tbu_para_indice_ignu(self):
        zona = self._criar_zona_com_sensores(especie="suinos", indice="IGNU")
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        self._equipamento_sensor(zona["id"], "TGN-A", "tgn")
        self.leituras_simuladas = {"TBS-A": 28.0, "TBU-A": 22.0, "TGN-A": 30.0}

        resultado = self.servico.calcular(zona["id"])

        # tpo deve ter sido derivado (nao ha sensor de tpo cadastrado)
        self.assertIn("tpo", resultado["entradas"])
        self.assertEqual("IGNU", resultado["indice"])

    def test_falha_ao_acionar_atuador_nao_impede_o_calculo(self):
        zona = self._criar_zona_com_sensores()
        db.salvar_configuracoes({"habilitarEquipamentos": True})
        db.salvar_controle_zona(
            zona["id"], {"modo": "manual", "acionamento_habilitado": True}
        )
        self._equipamento_sensor(zona["id"], "TBS-A", "tbs")
        self._equipamento_sensor(zona["id"], "TBU-A", "tbu")
        db.criar_equipamento(zona["id"], {
            "tipo": "ventilador", "nome": "VENT-QUEBRADO", "modo_conexao": "tcp", "host": "10.0.0.9",
            "tipo_registrador": "coil", "endereco_registrador": 0,
        })
        self.leituras_simuladas = {"TBS-A": 38.0, "TBU-A": 30.0}

        def escrever_falho(equipamento, ligar):
            return False

        self.servico._escrever_modbus_real = escrever_falho
        resultado = self.servico.calcular(zona["id"])

        self.assertIn("VENT-QUEBRADO", resultado["atuadores_com_falha"])
        self.assertIsNotNone(resultado["valor"])  # o calculo em si nao falhou


class TestModoSimuladoZonaService(unittest.TestCase):
    """Sem simulador injetado, o servico sempre usa as funcoes reais
    (default). Com um simulador injetado, a escolha entre real e simulado
    segue a configuracao `modoSimuladoZonas` persistida."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def test_sem_simulador_injetado_usa_sempre_a_funcao_real(self):
        chamadas_real = []

        def ler_real(equipamento):
            chamadas_real.append(equipamento["nome"])
            return 30.0

        servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            salvar_estado_equipamentos=_ignorar_estado_equipamentos,
            obter_controle_zona=db.obter_controle_zona,
            ler_modbus_real=ler_real,
        )
        # mesmo com modoSimuladoZonas=True (padrao) persistido, sem
        # simulador injetado o servico nao tem como simular -- usa real.
        zona = db.criar_zona({"nome": "Z", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(zona["id"], {
            "tipo": "sensor", "nome": "TBS", "modo_conexao": "tcp", "host": "1",
            "tipo_registrador": "input", "endereco_registrador": 1, "campo_medido": "tbs",
        })
        db.criar_equipamento(zona["id"], {
            "tipo": "sensor", "nome": "TBU", "modo_conexao": "tcp", "host": "1",
            "tipo_registrador": "input", "endereco_registrador": 2, "campo_medido": "tbu",
        })
        servico.calcular(zona["id"])
        self.assertIn("TBS", chamadas_real)

    def test_com_simulador_e_config_ligada_usa_simulado(self):
        db.salvar_configuracoes({"modoSimuladoZonas": True})

        class SimuladorFalso:
            def __init__(self):
                self.leituras_chamadas = []

            def ler_valor(self, equipamento):
                self.leituras_chamadas.append(equipamento["nome"])
                return 25.0

            def escrever_valor(self, equipamento, ligar):
                return True

            def registrar_calculo(self, *args, **kwargs):
                pass

        simulador = SimuladorFalso()
        chamadas_real = []

        def ler_real(equipamento):
            chamadas_real.append(equipamento["nome"])
            return 99.0

        servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            salvar_estado_equipamentos=_ignorar_estado_equipamentos,
            obter_controle_zona=db.obter_controle_zona,
            ler_modbus_real=ler_real,
        )
        servico.definir_simulador(simulador)

        zona = db.criar_zona({"nome": "Z", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(zona["id"], {
            "tipo": "sensor", "nome": "TBS", "modo_conexao": "tcp", "host": "1",
            "tipo_registrador": "input", "endereco_registrador": 1, "campo_medido": "tbs",
        })
        db.criar_equipamento(zona["id"], {
            "tipo": "sensor", "nome": "TBU", "modo_conexao": "tcp", "host": "1",
            "tipo_registrador": "input", "endereco_registrador": 2, "campo_medido": "tbu",
        })
        resultado = servico.calcular(zona["id"])

        self.assertIn("TBS", simulador.leituras_chamadas)
        self.assertEqual([], chamadas_real)
        self.assertTrue(resultado["modo_simulado"])

    def test_com_simulador_mas_config_desligada_usa_real(self):
        db.salvar_configuracoes({"modoSimuladoZonas": False})

        class SimuladorFalso:
            def ler_valor(self, equipamento):
                return 25.0

            def escrever_valor(self, equipamento, ligar):
                return True

            def registrar_calculo(self, *args, **kwargs):
                pass

        chamadas_real = []

        def ler_real(equipamento):
            chamadas_real.append(equipamento["nome"])
            return 30.0

        servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            salvar_estado_equipamentos=_ignorar_estado_equipamentos,
            obter_controle_zona=db.obter_controle_zona,
            ler_modbus_real=ler_real,
        )
        servico.definir_simulador(SimuladorFalso())

        zona = db.criar_zona({"nome": "Z", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(zona["id"], {
            "tipo": "sensor", "nome": "TBS", "modo_conexao": "tcp", "host": "1",
            "tipo_registrador": "input", "endereco_registrador": 1, "campo_medido": "tbs",
        })
        db.criar_equipamento(zona["id"], {
            "tipo": "sensor", "nome": "TBU", "modo_conexao": "tcp", "host": "1",
            "tipo_registrador": "input", "endereco_registrador": 2, "campo_medido": "tbu",
        })
        resultado = servico.calcular(zona["id"])

        self.assertIn("TBS", chamadas_real)
        self.assertFalse(resultado["modo_simulado"])


class TestPersistenciaEstadoEquipamentos(unittest.TestCase):
    """O servico persiste o estado atual dos atuadores a cada calculo,
    permitindo que o painel executivo seja montado a partir do banco."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path_original = db.DB_PATH
        db.DB_PATH = os.path.join(self.tempdir.name, "historico.db")
        db.iniciar_banco()

        self.leituras_simuladas: dict[str, float | None] = {}
        self.chamadas_estado: list[tuple] = []

        def ler_mock(equipamento):
            return self.leituras_simuladas.get(equipamento["nome"])

        def escrever_mock(equipamento, ligar):
            return True

        def salvar_estado_mock(
            zona_id,
            ventilador_ligado,
            nebulizador_ligado,
            intensidade,
            ventilador_desejado,
            nebulizador_desejado,
            ventilador_confirmado,
            nebulizador_confirmado,
            falhas,
            qualidade,
        ):
            self.chamadas_estado.append(
                (
                    zona_id,
                    ventilador_ligado,
                    nebulizador_ligado,
                    intensidade,
                    ventilador_desejado,
                    nebulizador_desejado,
                    ventilador_confirmado,
                    nebulizador_confirmado,
                    falhas,
                    qualidade,
                )
            )

        self.servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            obter_controle_zona=db.obter_controle_zona,
            ler_modbus_real=ler_mock,
            escrever_modbus_real=escrever_mock,
            salvar_estado_equipamentos=salvar_estado_mock,
        )

    def tearDown(self):
        db.DB_PATH = self.db_path_original
        self.tempdir.cleanup()

    def _criar_zona_com_sensores(self):
        zona = db.criar_zona({"nome": "Zona Teste", "especie": "frangos", "indice": "ITU"})
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "TBS-A",
                "modo_conexao": "tcp",
                "host": "10.0.0.1",
                "tipo_registrador": "input",
                "endereco_registrador": 1,
                "campo_medido": "tbs",
            },
        )
        db.criar_equipamento(
            zona["id"],
            {
                "tipo": "sensor",
                "nome": "TBU-A",
                "modo_conexao": "tcp",
                "host": "10.0.0.1",
                "tipo_registrador": "input",
                "endereco_registrador": 2,
                "campo_medido": "tbu",
            },
        )
        return zona

    def test_calcular_persiste_estado_consistente_com_o_resultado(self):
        zona = self._criar_zona_com_sensores()
        # Valores quentes o bastante para acionar ventilador e nebulizador
        # (mesmos valores de `test_atuadores_sao_acionados_conforme_status`
        # em TestZonaService, ja comprovados para essa transicao).
        self.leituras_simuladas = {"TBS-A": 38.0, "TBU-A": 30.0}

        resultado = self.servico.calcular(zona["id"])

        self.assertEqual(1, len(self.chamadas_estado))
        zona_id, ventilador_ligado, nebulizador_ligado, intensidade, *_ = (
            self.chamadas_estado[0]
        )
        self.assertEqual(zona["id"], zona_id)
        self.assertEqual(resultado["equipamento"]["ativo"], ventilador_ligado)
        self.assertEqual(resultado["equipamento"]["nebulizador"], nebulizador_ligado)
        self.assertEqual(resultado["equipamento"]["intensidade"], intensidade)
        self.assertTrue(ventilador_ligado)
        self.assertTrue(nebulizador_ligado)

    def test_calcular_manual_tambem_persiste_estado(self):
        zona = self._criar_zona_com_sensores()

        self.servico.calcular_manual(
            zona["id"], {"tbs": 38.0, "tbu": 30.0}
        )

        self.assertEqual(1, len(self.chamadas_estado))

    def test_dois_ciclos_atualizam_a_mesma_zona_sem_acumular_chamada_extra(self):
        zona = self._criar_zona_com_sensores()
        self.leituras_simuladas = {"TBS-A": 38.0, "TBU-A": 30.0}
        self.servico.calcular(zona["id"])
        self.leituras_simuladas = {"TBS-A": 20.0, "TBU-A": 16.0}

        resultado_2 = self.servico.calcular(zona["id"])

        self.assertEqual(2, len(self.chamadas_estado))
        # A segunda chamada reflete o resultado do SEGUNDO ciclo, nao um
        # resquicio do primeiro.
        self.assertEqual(resultado_2["equipamento"]["ativo"], self.chamadas_estado[1][1])

    def test_falha_ao_persistir_estado_nao_impede_o_calculo(self):
        zona = self._criar_zona_com_sensores()

        def salvar_estado_com_erro(*args):
            raise RuntimeError("banco indisponível")

        servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            obter_controle_zona=db.obter_controle_zona,
            ler_modbus_real=lambda equipamento: {"TBS-A": 25.0, "TBU-A": 20.0}.get(
                equipamento["nome"]
            ),
            escrever_modbus_real=lambda equipamento, ligar: True,
            salvar_estado_equipamentos=salvar_estado_com_erro,
        )

        resultado = servico.calcular(zona["id"])

        self.assertIn("status", resultado)

    def test_limpar_resfriador_remove_estado_ativo_da_zona(self):
        zona = db.criar_zona({"nome": "Zona 1", "especie": "frangos", "indice": "ITU"})
        servico = ZonaService(
            obter_zona=db.obter_zona,
            salvar_leitura=db.salvar_leitura,
            obter_configuracoes=db.obter_configuracoes,
            obter_historico=db.obter_historico_por_zona,
            salvar_estado_equipamentos=_ignorar_estado_equipamentos,
            obter_controle_zona=db.obter_controle_zona,
        )
        servico.resfriador_da_zona(zona["id"]).registrar_leitura("Perigo")
        self.assertTrue(servico.resfriador_da_zona(zona["id"]).estado()["ativo"])

        servico.limpar_resfriador(zona["id"])

        # Depois de limpo, `resfriador_da_zona` recria um Resfriamento novo
        # (desligado) para o mesmo id -- essencial para que um zona_id
        # reaproveitado (zona excluida e uma nova criada com o mesmo id)
        # nao herde o estado ligado de uma instancia anterior.
        self.assertFalse(servico.resfriador_da_zona(zona["id"]).estado()["ativo"])


if __name__ == "__main__":
    unittest.main()

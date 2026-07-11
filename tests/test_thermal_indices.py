# -*- coding: utf-8 -*-
"""
test_thermal_indices.py
========================
Testes de validacao: reproduz os exemplos numericos publicados nas Tabelas
5, 6 e 7 e na secao 4.3 da propria dissertacao, exatamente como o autor fez
na secao 4.2 ("Validacao dos Resultados Obtidos").

Rodar com:
    python -m unittest tests.test_thermal_indices -v
"""

import unittest

from conforto_termico.thermal_indices import (
    CAMPOS_POR_INDICE,
    INDICES_POR_ESPECIE,
    LIMITES,
    calcular_ignu,
    calcular_itu,
    calcular_ituv,
    calcular_ponto_orvalho,
    calcular_pressao_atmosferica,
    calcular_umidade_relativa,
    classificar_status,
)


class TestFormulas(unittest.TestCase):
    def test_itu_secao_4_3(self):
        # Secao 4.3: tbs 18,00-27,00 / tbu 15,00-19,00 -> ITU de 64,36 a 73,72
        self.assertAlmostEqual(calcular_itu(18.00, 15.00), 64.36, places=2)
        self.assertAlmostEqual(calcular_itu(27.00, 19.00), 73.72, places=2)

    def test_itu_tabela_5(self):
        # Tabela 5 (ITU - Frangos), alguns pares bulbo seco/umido -> ITU
        self.assertAlmostEqual(calcular_itu(43, 28), 91.72, places=2)
        self.assertAlmostEqual(calcular_itu(7, 33), 69.40, places=2)
        self.assertAlmostEqual(calcular_itu(36, 23), 83.08, places=2)

    def test_ignu_tabela_7(self):
        # Tabela 7 (IGNU - Frangos): Globo Negro / Ponto de Orvalho -> IGNU
        self.assertAlmostEqual(calcular_ignu(42, 8), 69.58, places=2)
        self.assertAlmostEqual(calcular_ignu(6, 14), 50.14, places=2)
        self.assertAlmostEqual(calcular_ignu(37, 45), 79.90, places=2)

    def test_ituv_tabela_6(self):
        # Tabela 6 (ITUV - Frangos): bulbo seco / umido / velocidade do ar -> ITUV
        self.assertAlmostEqual(calcular_ituv(17, 13, 1.00), 16.40, places=1)
        self.assertAlmostEqual(calcular_ituv(22, 1, 4.00), 17.39, places=1)
        self.assertAlmostEqual(calcular_ituv(27, 21, 4.00), 24.08, places=1)
        self.assertAlmostEqual(calcular_ituv(44, 13, 1.00), 39.35, places=1)

    def test_psicrometria_calcula_umidade_e_ponto_de_orvalho(self):
        self.assertAlmostEqual(calcular_pressao_atmosferica(0), 101.325, places=3)
        self.assertAlmostEqual(calcular_umidade_relativa(25, 20, 0), 63.0, places=1)
        self.assertAlmostEqual(calcular_ponto_orvalho(25, 20, 0), 17.5, places=1)


class TestClassificacao(unittest.TestCase):
    def test_itu_frangos(self):
        # Tabela 4: Conforto <74, Alerta 74-79, Perigo 79-84, Emergencia >84
        self.assertEqual(classificar_status(73.72, "frangos", "ITU"), "Conforto")
        self.assertEqual(classificar_status(76.60, "frangos", "ITU"), "Alerta")
        self.assertEqual(classificar_status(83.08, "frangos", "ITU"), "Perigo")
        self.assertEqual(classificar_status(91.72, "frangos", "ITU"), "Emergência")

    def test_itu_bovinos(self):
        # Tabela 4: Conforto <=70, Alerta 71-78, Perigo 79-83, Emergencia >83
        self.assertEqual(classificar_status(65.0, "bovinos", "ITU"), "Conforto")
        self.assertEqual(classificar_status(75.0, "bovinos", "ITU"), "Alerta")
        self.assertEqual(classificar_status(81.0, "bovinos", "ITU"), "Perigo")
        self.assertEqual(classificar_status(90.0, "bovinos", "ITU"), "Emergência")

    def test_ituv_frangos(self):
        # Tabela 4: Conforto <=24, Alerta <=34, Perigo <=39, Emergencia >39
        self.assertEqual(classificar_status(16.40, "frangos", "ITUV"), "Conforto")
        self.assertEqual(classificar_status(24.08, "frangos", "ITUV"), "Alerta")
        self.assertEqual(classificar_status(35.98, "frangos", "ITUV"), "Perigo")
        self.assertEqual(classificar_status(39.35, "frangos", "ITUV"), "Emergência")

    def test_ignu_frangos_binario(self):
        # Teixeira (1983): so existem "Conforto" (<=76) e "Emergencia" (>76)
        self.assertEqual(classificar_status(69.58, "frangos", "IGNU"), "Conforto")
        self.assertEqual(classificar_status(79.90, "frangos", "IGNU"), "Emergência")

    def test_indice_nao_disponivel_para_especie(self):
        with self.assertRaises(Exception):
            classificar_status(30.0, "bovinos", "ITUV")


class TestEstabilidadeConfiguracaoImutavel(unittest.TestCase):
    """As tabelas de configuracao compartilhada (LIMITES,
    INDICES_POR_ESPECIE, CAMPOS_POR_INDICE, etc.) sao estado de processo
    unico, reutilizado em toda requisicao HTTP. `_congelar` as protege com
    `MappingProxyType` para que uma tentativa de mutacao (por bug ou
    modificacao futura descuidada) falhe imediatamente com TypeError em
    vez de corromper silenciosamente o comportamento do app para todo
    mundo ate o proximo restart."""

    def test_limites_e_somente_leitura_no_nivel_superior(self):
        with self.assertRaises(TypeError):
            LIMITES["ITU"] = {}

    def test_limites_e_somente_leitura_em_niveis_aninhados(self):
        with self.assertRaises(TypeError):
            LIMITES["ITU"]["frangos"]["conforto"] = 0

    def test_indices_por_especie_e_somente_leitura(self):
        with self.assertRaises(TypeError):
            INDICES_POR_ESPECIE["frangos"] = ()

    def test_campos_por_indice_e_somente_leitura(self):
        with self.assertRaises(TypeError):
            CAMPOS_POR_INDICE["ITU"] = ()

    def test_leitura_normal_continua_funcionando(self):
        # Congelar nao deve impedir o uso normal (leitura) dessas
        # estruturas -- apenas a escrita.
        self.assertEqual(74, LIMITES["ITU"]["frangos"]["conforto"])
        self.assertIn("ITU", INDICES_POR_ESPECIE["frangos"])


if __name__ == "__main__":
    unittest.main()

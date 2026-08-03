import unittest

from tests.categories import unclassified_test_modules


class TestClassificacaoDaSuite(unittest.TestCase):
    def test_todo_modulo_de_teste_tem_categoria_de_risco_ou_finalidade(self):
        self.assertFalse(unclassified_test_modules())

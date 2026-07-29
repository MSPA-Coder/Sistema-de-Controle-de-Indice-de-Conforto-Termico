"""
test_cache.py
=============
Testes unitários para o módulo de cache com TTL.
"""

import unittest

from app.cache import CacheComTTL, obter_cache, resetar_cache_global


class TestCacheComTTL(unittest.TestCase):
    """Testes para a classe CacheComTTL."""

    def setUp(self):
        """Configura um cache fresco para cada teste."""
        self.cache = CacheComTTL(ttl_segundos=1.0)

    def tearDown(self):
        """Limpa o cache após cada teste."""
        self.cache.clear()

    def test_set_e_get_basico(self):
        """Testa armazenamento e recuperação básica."""
        self.cache.set("chave1", "valor1")
        self.assertEqual(self.cache.get("chave1"), "valor1")

    def test_get_chave_inexistente(self):
        """Testa obtenção de chave que não existe."""
        self.assertIsNone(self.cache.get("nao_existe"))

    def test_delete_chave_existente(self):
        """Testa remoção de chave existente."""
        self.cache.set("chave1", "valor1")
        self.assertTrue(self.cache.delete("chave1"))
        self.assertIsNone(self.cache.get("chave1"))

    def test_delete_chave_inexistente(self):
        """Testa remoção de chave que não existe."""
        self.assertFalse(self.cache.delete("nao_existe"))

    def test_clear_limpa_todo_cache(self):
        """Testa que clear remove todas as entradas."""
        self.cache.set("chave1", "valor1")
        self.cache.set("chave2", "valor2")
        self.cache.clear()
        self.assertIsNone(self.cache.get("chave1"))
        self.assertIsNone(self.cache.get("chave2"))

    def test_stats_retorna_estatisticas(self):
        """Testa estatísticas de hits e misses."""
        self.cache.set("chave1", "valor1")
        self.cache.get("chave1")  # hit
        self.cache.get("chave1")  # hit
        self.cache.get("chave2")  # miss

        stats = self.cache.stats()
        self.assertEqual(stats["hits"], 2)
        self.assertEqual(stats["misses"], 1)
        self.assertEqual(stats["hit_rate"], 66.67)
        self.assertEqual(stats["tamanho"], 1)

    def test_ttl_expiracao(self):
        """Testa expiração por TTL."""
        cache_curto = CacheComTTL(ttl_segundos=0.5)
        cache_curto.set("chave_temp", "valor_temp")

        # Deve existir imediatamente
        self.assertEqual(cache_curto.get("chave_temp"), "valor_temp")

        # Espera expirar
        import time
        time.sleep(0.6)

        # Deve ter expirado
        self.assertIsNone(cache_curto.get("chave_temp"))

    def test_invalidate_pattern(self):
        """Testa invalidação por padrão."""
        self.cache.set("config_zona_1", {"id": 1})
        self.cache.set("config_zona_2", {"id": 2})
        self.cache.set("usuario_admin", {"role": "admin"})

        removidos = self.cache.invalidate_pattern("config_")

        self.assertEqual(removidos, 2)
        self.assertIsNone(self.cache.get("config_zona_1"))
        self.assertIsNone(self.cache.get("config_zona_2"))
        self.assertIsNotNone(self.cache.get("usuario_admin"))

    def test_cached_decorator(self):
        """Testa decorador de cache."""
        chamadas = [0]

        @self.cache.cached("teste_")
        def funcao_cara(x, y):
            chamadas[0] += 1
            return x + y

        # Primeira chamada - executa função
        resultado1 = funcao_cara(2, 3)
        self.assertEqual(resultado1, 5)
        self.assertEqual(chamadas[0], 1)

        # Segunda chamada com mesmos args - usa cache
        resultado2 = funcao_cara(2, 3)
        self.assertEqual(resultado2, 5)
        self.assertEqual(chamadas[0], 1)  # Não incrementou

        # Chamada com args diferentes - executa função
        resultado3 = funcao_cara(3, 4)
        self.assertEqual(resultado3, 7)
        self.assertEqual(chamadas[0], 2)


class TestCacheGlobal(unittest.TestCase):
    """Testes para funções de cache global."""

    def setUp(self):
        """Reseta cache global antes de cada teste."""
        resetar_cache_global()

    def tearDown(self):
        """Reseta cache global após cada teste."""
        resetar_cache_global()

    def test_obter_cache_singleton(self):
        """Testa que obter_cache retorna singleton."""
        cache1 = obter_cache()
        cache2 = obter_cache()
        self.assertIs(cache1, cache2)

    def test_resetar_cache_global(self):
        """Testa reset do cache global."""
        cache1 = obter_cache()
        cache1.set("teste", "valor")

        resetar_cache_global()

        cache2 = obter_cache()
        self.assertIsNone(cache2.get("teste"))


if __name__ == "__main__":
    unittest.main()

"""Infraestrutura transversal, sem regra de negócio.

Conexão ao PostgreSQL (``db_backend``), cache em memória com TTL, disjuntor
para as chamadas ao Coletor, leitura do ``.env`` e a fila assíncrona de
e-mail de alerta. Nada aqui conhece zona, sensor ou índice de conforto.
"""

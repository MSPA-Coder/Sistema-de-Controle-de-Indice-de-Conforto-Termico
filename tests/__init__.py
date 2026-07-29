"""Testes automatizados do projeto."""

import os

# Ligado uma única vez, antes de qualquer submódulo `tests.test_*` importar
# uma fábrica de app (`criar_app_ict`/`criar_app_coletor`) ou o `app` de
# módulo em `run_ict.py`. Faz `app.testing` ser `True` por padrão nas apps
# de teste, o que dispensa CSRF (ver `auth._proteger_csrf`) sem acoplar essa
# decisão ao backend de persistência ativo (SQLite ou PostgreSQL). Nunca é
# definido fora da suíte: produção/Docker não passam por este pacote.
# `setdefault` preserva um valor já definido pelo ambiente de CI/execução.
os.environ.setdefault("CONFORTO_TESTING", "1")

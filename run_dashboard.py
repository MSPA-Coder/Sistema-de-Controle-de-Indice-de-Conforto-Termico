# -*- coding: utf-8 -*-
"""Lançador do processo DASHBOARD (só leitura: análises e histórico, sem
Modbus) -- FASE 1 da separação coletor/dashboard (ver `agents.md`).

Para rodar:
    python run_dashboard.py

Por padrão sobe em http://127.0.0.1:5000 -- se for rodar junto com
`run_coletor.py` na MESMA máquina, dê a cada um uma porta diferente:

    CONFORTO_PORT=5000 python run_coletor.py
    CONFORTO_PORT=5001 python run_dashboard.py

Este processo nunca importa `modbus_client`/`zona_service` (ver
`app_factory.criar_app` e `tests/test_app_factory.py`) -- mesmo que um bug
tentasse usar essas peças por engano, elas simplesmente não existem na
memória deste processo."""

from conforto_termico.app_factory import AppConfig, criar_app, executar_servidor

config = AppConfig.from_env()
app = criar_app(papel_app="dashboard", config=config)


if __name__ == "__main__":
    executar_servidor(app, config)

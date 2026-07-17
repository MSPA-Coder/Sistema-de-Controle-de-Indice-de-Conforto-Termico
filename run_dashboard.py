# -*- coding: utf-8 -*-
"""Lancador do processo DASHBOARD (so leitura: analises e historico, sem
Modbus) -- FASE 1 da separacao coletor/dashboard (ver `agents.md`).

Para rodar:
    python run_dashboard.py

Por padrao sobe em http://127.0.0.1:5001, conforme `config/servidor.json`.
Os `CONFORTO_*` continuam valendo e sobrescrevem o arquivo quando
definidos.

Este processo nunca importa `modbus_client`/`zona_service` (ver
`app_factory.criar_app` e `tests/test_app_factory.py`) -- mesmo que um bug
tentasse usar essas pecas por engano, elas simplesmente nao existem na
memoria deste processo."""

from conforto_termico.app_factory import AppConfig, criar_app, executar_servidor

config = AppConfig.from_env("dashboard")
app = criar_app(papel_app="dashboard", config=config)


if __name__ == "__main__":
    executar_servidor(app, config)

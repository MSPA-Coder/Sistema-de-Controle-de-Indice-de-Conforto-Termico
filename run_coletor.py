# -*- coding: utf-8 -*-
"""Lançador do processo COLETOR (fala Modbus, calcula o índice, grava no
banco) -- FASE 1 da separação coletor/dashboard (ver `agents.md`).

Para rodar:
    python run_coletor.py

Por padrão sobe em http://127.0.0.1:5000 -- os mesmos `CONFORTO_*` de
sempre continuam valendo (`CONFORTO_PORT`, `CONFORTO_HOST`, etc.; ver
`app_factory.AppConfig`). Se for rodar coletor e dashboard na MESMA
máquina ao mesmo tempo, dê a cada um uma porta diferente, por exemplo:

    CONFORTO_PORT=5000 python run_coletor.py
    CONFORTO_PORT=5001 python run_dashboard.py

Os dois processos apontam para o mesmo arquivo `instance/historico.db`
por padrão (nenhuma variável extra necessária) -- o WAL + timeout de
`database._conexao` já cobre dois processos escrevendo/lendo o mesmo
arquivo ao mesmo tempo."""

from conforto_termico.app_factory import AppConfig, criar_app, executar_servidor

config = AppConfig.from_env()
app = criar_app(papel_app="coletor", config=config)


if __name__ == "__main__":
    executar_servidor(app, config)

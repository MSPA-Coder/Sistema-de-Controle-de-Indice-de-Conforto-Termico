# -*- coding: utf-8 -*-
"""Lancador do processo COLETOR (fala Modbus, calcula o indice e grava no
banco).

Para rodar:
    python run_coletor.py

Por padrao sobe em http://127.0.0.1:5000, conforme `config/servidor.json`.
Os mesmos `CONFORTO_*` de sempre continuam valendo (`CONFORTO_PORT`,
`CONFORTO_HOST`, etc.; ver `app_factory.AppConfig`) e sobrescrevem o
arquivo quando definidos.

Os dois processos apontam para o mesmo arquivo `instance/historico.db`
por padrao (nenhuma variavel extra necessaria) -- o WAL + timeout de
`database._conexao` ja cobre dois processos escrevendo/lendo o mesmo
arquivo ao mesmo tempo."""

from app.app_factory import AppConfig, criar_app, executar_servidor

config = AppConfig.from_env("coletor")
app = criar_app(papel_app="coletor", config=config)


if __name__ == "__main__":
    executar_servidor(app, config)

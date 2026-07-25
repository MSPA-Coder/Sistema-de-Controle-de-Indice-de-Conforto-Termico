# -*- coding: utf-8 -*-
"""Lançador do serviço privado COLETOR.

Para rodar:
    python run_coletor.py

Executa a malha contínua e uma API HTTP interna autenticada. Não serve
interface de usuário e não deve publicar sua porta fora da rede Docker.
"""

from app.app_factory import AppConfig, criar_app_coletor, executar_coletor

config = AppConfig.from_env("coletor")
app = criar_app_coletor(config)


if __name__ == "__main__":
    executar_coletor(app, config)

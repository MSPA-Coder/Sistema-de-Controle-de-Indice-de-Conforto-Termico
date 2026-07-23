# -*- coding: utf-8 -*-
"""
web.py
======
Compoe coletor e dashboard no mesmo processo para a execucao padrao por
`app.py`. As rotas vivem nos respectivos Blueprints e os servicos com
estado ficam em `coletor/estado.py`.
"""

from __future__ import annotations

from .app_factory import AppConfig, criar_app, executar_servidor

_config = AppConfig.from_env()
app = criar_app(papel_app=None, config=_config)


def executar_servidor_local(config: AppConfig | None = None) -> None:
    """Executa o servidor local sem o reloader do Werkzeug.

    Aceitar `config` como parametro (em vez de ler `os.environ`
    diretamente aqui) torna essa funcao testavel de forma deterministica,
    sem depender de variaveis de ambiente do shell de quem roda os
    testes."""
    executar_servidor(app, config or _config)


if __name__ == "__main__":
    executar_servidor_local()

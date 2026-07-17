# -*- coding: utf-8 -*-
"""
web.py
======
FASE 0 -- composicao "tudo num processo so": registra o Blueprint do
coletor E do dashboard no MESMO app Flask, preservando o comportamento de
hoje (um unico processo, uma unica porta, um unico banco). As rotas em si
vivem em `coletor/rotas.py`, `dashboard/rotas.py` e `rotas_comuns.py`; os
servicos com estado (ZonaService, etc.) vivem em `coletor/estado.py`. Este
modulo so compoe as pecas -- ver `app_factory.criar_app` para o raciocinio
completo de cada peca estar onde esta.

Tambem preserva, por compatibilidade, os nomes que os testes e o `app.py`
da raiz do projeto ja esperam encontrar aqui (`app`, `zona_service`,
`_resfriador`, `AppConfig`, `executar_servidor_local`, etc.) -- sao
reexports dos MESMOS objetos criados em `coletor/estado.py` e
`app_factory.py`, nao copias.

FASE 1 (`run_coletor.py`/`run_dashboard.py`, na raiz do projeto) usa a
MESMA `criar_app`, so que com `papel_app="coletor"`/`"dashboard"`, cada
processo com o seu proprio Blueprint -- ver `agents.md`, secao de
arquitetura, para o plano completo de migracao.

Para rodar (fase 0, um processo so):
    pip install -r requirements.txt
    python app.py
Depois abra http://127.0.0.1:5000 no navegador.
"""

from __future__ import annotations

from .app_factory import AppConfig, MENSAGEM_ERRO_INTERNO, criar_app, executar_servidor
from .coletor.estado import (
    _resfriador,
    calculo_ict_service,
    gerenciador_controle,
    historico_grafico_service,
    sensor_simulado_service,
    zona_service,
    zona_simulador,
)

_config = AppConfig.from_env()
app = criar_app(papel_app=None, config=_config)


def executar_servidor_local(config: AppConfig | None = None) -> None:
    """Executa o servidor local (fase 0, um processo so) sem o reloader do
    Werkzeug -- ver `app_factory.executar_servidor` para o motivo.

    Aceitar `config` como parametro (em vez de ler `os.environ`
    diretamente aqui) torna essa funcao testavel de forma deterministica,
    sem depender de variaveis de ambiente do shell de quem roda os
    testes."""
    executar_servidor(app, config or _config)


if __name__ == "__main__":
    executar_servidor_local()

"""Recusa instantânea de conexão com o PostgreSQL de teste.

`DATABASE_URL` nas fixtures desta suíte aponta para `localhost:5999`, porta
em que nada escuta -- de propósito, para as rotas que tocam o banco (ex.:
`/health`) verem uma falha de verdade em vez de um mock. Em Linux isso basta:
o SO recusa o `connect()` na hora e o driver levanta `OperationalError` de
imediato.

Em Windows, com psycopg 3.2.13 e Python 3.14, não basta. A recusa chega só em
`exceptfds` do `select()`, e `psycopg.waiting.wait_conn` -- o laço que
`psycopg.connection.connect()` usa para aguardar o socket ficar pronto -- só
olha `readfds`/`writefds`; o evento de erro nunca é observado e o laço gira
para sempre. `faulthandler.dump_traceback_later` confirma a pilha presa em
`selectors.py:_select` → `psycopg/waiting.py:wait_conn` →
`psycopg/connection.py:connect`. `connect_timeout` na URI não ajuda: o prazo
é conferido dentro do mesmo laço que nunca acorda.

A saída é não deixar o psycopg abrir socket nenhum. O `creator` do
SQLAlchemy substitui a função que a `Engine` chama para obter uma conexão
DBAPI; instalando um que recusa na hora, a suíte reproduz -- em qualquer
plataforma e sem esperar round-trip nenhum de rede -- exatamente a exceção
(`psycopg.OperationalError`) que o SQLAlchemy propagaria de um banco
inalcançável de verdade. `/health` continua respondendo 503 pelo motivo
certo: o banco está fora do ar, só que a suíte não perde minutos descobrindo
isso no Windows.

`app/nucleo/db_backend.py` importa `create_engine` de dentro da função `_engine`
(`from sqlalchemy import create_engine`), e essa `Engine` é cacheada por URL
(`lru_cache`) para o processo inteiro de teste -- por isso o patch precisa
estar no lugar antes da primeira conexão de cada teste, e por isso um único
`creator` instalado na primeira chamada já cobre as chamadas seguintes com a
mesma URL.
"""

from __future__ import annotations

import psycopg
import sqlalchemy
from _pytest.monkeypatch import MonkeyPatch


def _banco_inalcancavel(*_args: object, **_kwargs: object) -> object:
    raise psycopg.OperationalError(
        "suite de testes sem banco: conexao recusada (localhost:5999)"
    )


def recusar_conexao_com_banco(monkeypatch: MonkeyPatch) -> None:
    """Faz toda `Engine` criada por `sqlalchemy.create_engine` recusar conexão.

    Chame antes de `criar_app_ict()`/`criar_app_coletor()`: a fábrica cria o
    engine (via `app.nucleo.db_backend._engine`) na primeira consulta feita por uma
    rota, não no momento da criação da app -- mas o patch precisa estar no
    ar antes disso acontecer.
    """
    create_engine_original = sqlalchemy.create_engine

    def _create_engine_sem_socket(url, **kwargs):
        kwargs["creator"] = _banco_inalcancavel
        return create_engine_original(url, **kwargs)

    monkeypatch.setattr(sqlalchemy, "create_engine", _create_engine_sem_socket)

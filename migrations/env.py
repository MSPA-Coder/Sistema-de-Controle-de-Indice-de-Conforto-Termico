from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.nucleo.db_backend import database_url

config = context.config
if config.config_file_name is not None:
    # `disable_existing_loggers=False` não é detalhe: o padrão do `fileConfig`
    # é True, e ele DESLIGA todo logger que já exista no processo -- inclusive
    # os da aplicação.
    #
    # Aqui isso nunca apareceu, porque o job `schema` aplica as migrações como
    # processo separado, que morre em seguida. Aparece no instante em que
    # alguém aplicar migração dentro do mesmo processo -- num teste, num script
    # de manutenção -- e o sintoma é a aplicação parar de registrar log em
    # silêncio, sem erro nenhum. Foi assim que um teste sem relação nenhuma
    # reprovou no MegaSena, onde o mesmo padrão existia.
    #
    # Manter os loggers existentes é a recomendação da própria documentação do
    # Alembic para este caso, e não deixa de configurar nada: os loggers
    # declarados no `alembic.ini` continuam sendo aplicados.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = database_url()
if not url:
    raise RuntimeError("A configuração PostgreSQL é obrigatória para executar o Alembic.")
config.set_main_option("sqlalchemy.url", url)

target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

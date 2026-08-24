import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Модели импортируются ради побочного действия: объявление таблицы
# регистрирует её в метаданных, по которым alembic и сверяет базу.
import app.db.models  # noqa: F401

config = context.config

if config.config_file_name is not None and not config.attributes.get(
    "connection"
):
    fileConfig(config.config_file_name)

# Автогенерация сверяет базу с этими таблицами, поэтому источник схемы
# один — модели приложения.
target_metadata = SQLModel.metadata


def _sync_url() -> str:
    """Адрес для синхронного драйвера.

    Alembic работает синхронно, а приложение — асинхронно, поэтому из
    адреса убирается имя асинхронного драйвера. Так обе стороны
    настраиваются одной переменной.
    """
    url = os.environ.get("DATABASE_URL", "sqlite:///alembic.sqlite")
    return url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg")


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # sqlite не умеет менять колонку через ALTER, поэтому правки
        # выполняются пересозданием таблицы. Без этого флага миграция,
        # меняющая колонку, падает на sqlite и работает на postgres —
        # то есть ломается только там, где её сложнее заметить.
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Соединение может прийти снаружи: приложение прогоняет миграции на
    # своём, потому что база в памяти существует только внутри него.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_url()
    engine = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    with engine.connect() as own_connection:
        _run(own_connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

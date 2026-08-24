from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import StaticPool
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import Settings

ROOT = Path(__file__).resolve().parents[2]


def create_engine(settings: Settings) -> AsyncEngine:
    # StaticPool для базы в памяти: у каждого соединения sqlite своя
    # in-memory база, поэтому без общего соединения приложение и
    # миграции работали бы с разными базами.
    if settings.database_url.endswith("://"):
        return create_async_engine(
            settings.database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    return create_async_engine(settings.database_url)


def _upgrade(connection: Connection) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    # Соединение передаётся через attributes: migrations/env.py берёт его
    # оттуда вместо того, чтобы поднимать своё. Для базы в памяти это
    # обязательно — своё соединение увидело бы пустую базу.
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


async def migrate(engine: AsyncEngine) -> None:
    """Схему создают миграции, а не metadata.create_all.

    Так у схемы один источник — файлы в migrations/, — и каждый запуск
    приложения прогоняет их заново. Сломанная миграция роняет старт, а не
    всплывает у того, кто однажды накатит её на боевую базу.
    """
    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    # Сессия берётся у SQLModel, а не у SQLAlchemy: у неё `exec()`,
    # который знает тип выбираемой модели, поэтому результат запроса
    # типизирован без приведений.
    return async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

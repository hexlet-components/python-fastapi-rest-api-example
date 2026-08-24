from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Сессия базы на запрос.

    Фабрика лежит в состоянии приложения, а не в модуле: тесты подменяют
    зависимость на сессию внутри своей транзакции и откатывают её,
    поэтому источник сессии должен быть один и снаружи заменяемый.
    """
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

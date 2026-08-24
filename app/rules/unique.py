from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession


async def is_unique(session: AsyncSession, column, value: object) -> bool:
    """Единственное правило, которое нельзя выразить в контракте.

    Уникальность зависит от состояния базы, поэтому её не проверить ни
    типом поля, ни ограничением в спеке — нужен запрос.
    """
    found = await session.scalar(select(column).where(col(column) == value))
    return found is None

from typing import Any, Protocol

from fastapi_pagination import Page, Params
from fastapi_pagination.ext.sqlmodel import apaginate
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import Select, SelectOfScalar


class PageQuery(Protocol):
    """Постраничный вход любой операции контракта.

    Границы и значения по умолчанию объявлены в контракте, поэтому у
    каждой операции своя сгенерированная модель запроса — а считают
    страницу они одинаково.
    """

    page: int | None
    size: int | None


async def fetch_page(
    session: AsyncSession,
    statement: Select[Any] | SelectOfScalar[Any],
    query: PageQuery,
) -> Page[Any]:
    """Страница выборки: срез и общее число считает fastapi-pagination.

    Форма страницы (`page`, `size`, `total`, `pages`) задана контрактом
    и совпадает с формой библиотеки, поэтому её метаданные уходят в
    ответ как есть. Порядок в выборке должен быть задан явно: без него
    база его не обещает, и страницы могут пересекаться.
    """
    return await apaginate(
        session,
        statement,
        params=Params(page=query.page or 1, size=query.size or 10),
    )

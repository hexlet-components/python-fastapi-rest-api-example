from typing import Annotated

from fastapi import HTTPException, Query, Response, status
from sqlmodel import col, delete, func, select, update

from app.db.models import Course, User
from app.db.projections import PUBLIC_USER_COLUMNS
from app.dependencies import SessionDep, SettingsDep
from app.lib.changes import changes
from app.lib.identifiers import ResourceId
from app.lib.pagination import Paging
from app.lib.password import hash_password
from app.lib.serialization import to_schema
from app.types.handlers.v1 import pydantic_gen as contract
from app.validators import users as validator

UserId = ResourceId


async def find_public_user(session: SessionDep, user_id: int, columns=None):
    """Пользователь в публичной проекции.

    Проекция вместо строки целиком: рядом лежит password_digest, и
    выбирать его незачем ни для ответа, ни для проверки существования.
    Набор колонок передаётся аргументом — у второй версии контракта он
    свой.
    """
    row = (
        await session.exec(
            select(*(columns or PUBLIC_USER_COLUMNS)).where(
                col(User.id) == user_id
            )
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return row


async def count_users(session: SessionDep) -> int:
    return await session.scalar(select(func.count()).select_from(User))


async def index(
    session: SessionDep,
    query: Annotated[contract.UsersIndexQuery, Query()],
) -> contract.UserPage:
    paging = Paging.of(query)
    rows = (
        await session.exec(
            select(*PUBLIC_USER_COLUMNS)
            # Порядок задан явно: без него база его не обещает, и
            # «первая» запись до правки и после — не обязательно одна.
            .order_by(col(User.id))
            .limit(paging.limit)
            .offset(paging.offset)
        )
    ).all()

    return contract.UserPage(
        data=[to_schema(contract.User, row) for row in rows],
        meta=paging.meta(await count_users(session)),
    )


async def show(session: SessionDep, user_id: UserId) -> contract.User:
    return to_schema(contract.User, await find_public_user(session, user_id))


async def create(
    session: SessionDep,
    settings: SettingsDep,
    data: contract.UserCreateDto,
) -> contract.User:
    await validator.validate_create(session, data)

    digest = await hash_password(data.password, settings.scrypt_cost)
    user = User(
        full_name=data.full_name,
        email=data.email.lower(),
        password_digest=digest,
    )
    session.add(user)
    await session.commit()

    return to_schema(contract.User, user)


async def replace(
    session: SessionDep,
    settings: SettingsDep,
    user_id: UserId,
    data: contract.UserEditDto,
) -> contract.User:
    # Запись читается до правки: так 404 наступает раньше любой работы,
    # и есть что вернуть, если менять нечего.
    existing = await find_public_user(session, user_id)

    values = changes(data, schema="UserEditDTO")
    values.pop("password", None)
    if data.password is not None:
        values["password_digest"] = await hash_password(
            data.password, settings.scrypt_cost
        )

    if not values:
        return to_schema(contract.User, existing)

    await session.exec(
        update(User).where(col(User.id) == user_id).values(**values)
    )
    await session.commit()

    return to_schema(contract.User, await find_public_user(session, user_id))


async def destroy(session: SessionDep, user_id: UserId) -> Response:
    await find_public_user(session, user_id)

    # Курс не перестаёт существовать от того, что автор ушёл, поэтому
    # удаление отклоняется, а не сносит его содержимое. Кому достаются
    # осиротевшие курсы — продуктовое решение, и принимать его молча
    # обработчик не вправе.
    owned = await session.scalar(
        select(func.count())
        .select_from(Course)
        .where(col(Course.creator_id) == user_id)
    )
    if owned:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"User still owns {owned} course(s)"
        )

    await session.exec(delete(User).where(col(User.id) == user_id))
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Обработчики связываются с операциями контракта по идентификатору:
# маршруты вешает app/glue.py, читая спеку. Забытая или лишняя операция
# роняет приложение на старте.
handlers = {
    "usersIndex": index,
    "usersShow": show,
    "usersCreate": create,
    "usersUpdate": replace,
    "usersDestroy": destroy,
}

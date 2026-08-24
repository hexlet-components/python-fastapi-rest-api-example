from typing import Annotated

from fastapi import HTTPException, Query, Response, status
from sqlmodel import col, delete, func, select, update

from app.db.models import Course, User
from app.db.projections import PUBLIC_USER_COLUMNS_V2
from app.dependencies import SessionDep, SettingsDep
from app.lib.changes import changes
from app.lib.identifiers import ResourceId
from app.lib.pagination import Paging
from app.lib.password import hash_password
from app.lib.serialization import to_schema
from app.routers.users import count_users, find_public_user
from app.types.handlers.v2 import pydantic_gen as contract
from app.validators import users as validator

# Обработчики пользователей продублированы, а не собраны из первой
# версии условием: именно здесь версии контракта и расходятся. Во второй
# у пользователя есть phone — он принимается на запись и попадает в
# ответ, а проекция первой версии его не отдаёт. Модели тоже свои: они
# сгенерированы из документа второй версии.
#
# Курсы, уроки и токены между версиями не менялись, поэтому вторая
# версия подключает те же роутеры.

UserId = ResourceId


async def index(
    session: SessionDep,
    query: Annotated[contract.UsersIndexQuery, Query()],
) -> contract.UserPage:
    paging = Paging.of(query)
    rows = (
        await session.exec(
            select(*PUBLIC_USER_COLUMNS_V2)
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
    row = await find_public_user(session, user_id, PUBLIC_USER_COLUMNS_V2)
    return to_schema(contract.User, row)


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
        phone=data.phone,
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
    existing = await find_public_user(session, user_id, PUBLIC_USER_COLUMNS_V2)

    values = changes(data, schema="UserEditDTO", version="v2")
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

    row = await find_public_user(session, user_id, PUBLIC_USER_COLUMNS_V2)
    return to_schema(contract.User, row)


async def destroy(session: SessionDep, user_id: UserId) -> Response:
    await find_public_user(session, user_id, PUBLIC_USER_COLUMNS_V2)

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


handlers = {
    "usersIndex": index,
    "usersShow": show,
    "usersCreate": create,
    "usersUpdate": replace,
    "usersDestroy": destroy,
}

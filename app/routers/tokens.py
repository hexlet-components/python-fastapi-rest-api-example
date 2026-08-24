from fastapi import HTTPException, status
from sqlmodel import col, select

from app.db.models import User
from app.dependencies import SessionDep, SettingsDep
from app.lib.password import verify_password
from app.security import UNAUTHORIZED_HEADERS, create_token
from app.types.handlers.v1 import pydantic_gen as contract


async def create(
    session: SessionDep,
    settings: SettingsDep,
    data: contract.AuthInfo,
) -> contract.TokenInfo:
    user = (
        await session.exec(
            select(User).where(col(User.email) == data.email.lower())
        )
    ).first()

    # Один и тот же ответ на «нет такого адреса» и «неверный пароль»:
    # иначе операция превращается в проверку того, зарегистрирован ли
    # адрес.
    valid = user is not None and await verify_password(
        data.password, user.password_digest
    )
    if not valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid email or password",
            headers=UNAUTHORIZED_HEADERS,
        )

    return contract.TokenInfo(token=create_token(user.id, settings))


handlers = {"tokensCreate": create}

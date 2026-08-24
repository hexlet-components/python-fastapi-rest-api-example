from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import Depends, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import col, select

from app.db.models import User
from app.dependencies import SessionDep, SettingsDep
from app.lib.problems import problem_response
from app.settings import Settings

UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


class Unauthorized(Exception):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BearerAuth(HTTPBearer):
    """Схема авторизации, отвечающая 401, а не 403.

    Имя класса — это имя схемы в спеке, поэтому оно совпадает с именем
    из контракта (`BearerAuth`): по нему клиент находит, чем
    подписываться.

    Готовая схема на отсутствующий заголовок отдаёт 403, то есть
    «аутентифицирован, но не имею права». Отсутствие токена — это другое
    состояние, и клиенту нужен именно 401 с указанием схемы в
    WWW-Authenticate.
    """

    def __init__(self) -> None:
        super().__init__(auto_error=False)

    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials:
        credentials = await super().__call__(request)
        if credentials is None:
            raise Unauthorized("Authorization header with a bearer token")
        return credentials


bearer_scheme = BearerAuth()


def create_token(user_id: int, settings: Settings) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.jwt_expires_in
    )
    return jwt.encode(
        {"id": user_id, "exp": expires_at},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


async def current_user_id(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[
        HTTPAuthorizationCredentials, Security(bearer_scheme)
    ],
) -> int:
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as error:
        raise Unauthorized("Invalid or expired token") from error

    user_id = payload.get("id")
    if not isinstance(user_id, int):
        raise Unauthorized("Token carries no user identifier")

    # Токен живёт до истечения срока, а пользователя за это время могли
    # удалить. Без проверки запрос идёт дальше с идентификатором,
    # которого в базе нет, и падает на внешнем ключе уже в обработчике.
    found = await session.scalar(select(User.id).where(col(User.id) == user_id))
    if found is None:
        raise Unauthorized("Token refers to a user that no longer exists")

    return user_id


CurrentUserDep = Annotated[int, Depends(current_user_id)]


async def unauthorized_handler(request: Request, error: Unauthorized):
    return problem_response(
        status.HTTP_401_UNAUTHORIZED,
        error.detail,
        headers=UNAUTHORIZED_HEADERS,
    )

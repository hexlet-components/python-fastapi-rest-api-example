from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import User
from app.lib.problems import ValidationProblemError
from app.rules.unique import is_unique
from app.types.handlers.v1.pydantic_gen import (
    UnprocessableEntityErrorErrors,
    UserCreateDto,
)


async def validate_create(session: AsyncSession, data: UserCreateDto) -> None:
    """Правила предметной области, а не структура запроса.

    Структуру уже проверила схема операции, сгенерированная из
    контракта: типы, границы, обязательность. Здесь остаётся то, для
    чего нужна база.

    Валидатор один на обе версии контракта: вторая добавляет к
    пользователю phone, но правило уникальности адреса от этого не
    меняется.
    """
    errors = []
    if not await is_unique(session, User.email, data.email.lower()):
        errors.append(
            UnprocessableEntityErrorErrors(
                message="email is already taken",
                rule="unique",
                field="email",
            )
        )

    if errors:
        raise ValidationProblemError(errors)

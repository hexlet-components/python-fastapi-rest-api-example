import logging
from collections.abc import MutableMapping
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi_problem.error import (
    Problem,
    ServerProblem,
    StatusProblem,
    UnauthorisedProblem,
    UnprocessableProblem,
)
from fastapi_problem.handler import add_exception_handler, new_exception_handler
from starlette.requests import Request

from app.types.handlers.v1.pydantic_gen import UnprocessableEntityErrorErrors

MEDIA_TYPE = "application/problem+json"

# Тип проблемы — адрес описания статуса, как требует RFC 9457: без
# шаблона библиотека отдала бы выдуманные «http-not-found».
TYPE_URI = "https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/{status}"

logger = logging.getLogger(__name__)


def _title(code: HTTPStatus) -> str:
    return code.phrase


class ValidationProblemError(UnprocessableProblem):
    """Нарушено правило предметной области.

    Несёт список полей: клиенту нужно знать, какое поле и по какому
    правилу не прошло. Форма элемента задана контрактом.
    """

    title = _title(HTTPStatus.UNPROCESSABLE_CONTENT)

    def __init__(self, errors: list[UnprocessableEntityErrorErrors]) -> None:
        super().__init__(
            "Errors related to business logic such as uniqueness",
            errors=[_dump(error) for error in errors],
        )


class PreconditionFailed(StatusProblem):
    status = HTTPStatus.PRECONDITION_FAILED
    title = _title(HTTPStatus.PRECONDITION_FAILED)


class TooManyRequests(StatusProblem):
    status = HTTPStatus.TOO_MANY_REQUESTS
    title = _title(HTTPStatus.TOO_MANY_REQUESTS)


class Unauthorized(UnauthorisedProblem):
    """401 с указанием схемы.

    Отсутствие токена — не «нет прав» (403), а «не представились», и
    клиенту нужно знать, чем подписываться.
    """

    title = _title(HTTPStatus.UNAUTHORIZED)
    headers_ = {"WWW-Authenticate": "Bearer"}  # noqa: RUF012


class InternalError(ServerProblem):
    """500, в тело которого не попадает ничего из исключения.

    Библиотека по умолчанию кладёт в `detail` текст исключения, а он
    может содержать что угодно, вплоть до фрагмента запроса к базе.
    """

    title = _title(HTTPStatus.INTERNAL_SERVER_ERROR)

    def __init__(
        self,
        detail: str | None = None,
        headers: MutableMapping[str, str] | None = None,
    ) -> None:
        super().__init__(headers=headers)


def _dump(error: UnprocessableEntityErrorErrors) -> dict[str, str]:
    return error.model_dump(mode="json", exclude_none=True, by_alias=True)


def _describe(error: dict) -> UnprocessableEntityErrorErrors:
    # Первый элемент loc — часть запроса (body, query, path), и в имя
    # поля он не входит: клиент видит его из самой операции.
    location = [str(part) for part in error["loc"][1:]]
    return UnprocessableEntityErrorErrors(
        message=error["msg"],
        rule=error["type"],
        field=".".join(location),
    )


def _request_validation(
    _handler: object, _request: Request, error: RequestValidationError
) -> Problem:
    return UnprocessableProblem(
        "The request does not match the schema of the operation",
        errors=[_dump(_describe(item)) for item in error.errors()],
    )


def to_response(problem: Problem) -> JSONResponse:
    """Ответ для ошибки, возникшей вне обработчиков приложения.

    Промежуточные слои стоят снаружи обработчиков исключений, и их
    ошибки приходится отдавать самим — в том же формате.
    """
    return JSONResponse(
        status_code=problem.status,
        content=problem.marshal(uri=TYPE_URI, strict=True),
        media_type=MEDIA_TYPE,
        headers=problem.headers,
    )


def register_handlers(app: FastAPI) -> None:
    """Все ошибки приложения отдаются в одном формате.

    Фреймворк по умолчанию рисует свои: `{"detail": ...}`. В контракте
    же объявлен один тип тела на все ошибки. Обработчик библиотеки
    стоит на базовых `HTTPException` Starlette (им бросает сам
    фреймворк, например 400 на нечитаемом теле), на `Exception` и на
    `Problem`.
    """
    add_exception_handler(
        app,
        new_exception_handler(
            logger=logger,
            documentation_uri_template=TYPE_URI,
            strict_rfc9457=True,
            unhandled_wrappers={"500": InternalError},
            request_validation_handler=_request_validation,
        ),
        generic_swagger_defaults=False,
    )

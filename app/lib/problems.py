import logging
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as BaseHTTPException

from app.types.handlers.v1.pydantic_gen import (
    ProblemDetails,
    UnprocessableEntityError,
    UnprocessableEntityErrorErrors,
)

MEDIA_TYPE = "application/problem+json"

logger = logging.getLogger(__name__)


class ValidationProblemError(Exception):
    """Нарушено правило предметной области.

    Отдельно от HTTPException, потому что несёт список полей: клиенту
    нужно знать, какое поле и по какому правилу не прошло.
    """

    def __init__(self, errors: list[UnprocessableEntityErrorErrors]) -> None:
        super().__init__("Validation failed")
        self.errors = errors


class PreconditionFailed(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_412_PRECONDITION_FAILED, detail=detail
        )


def problem_response(
    status_code: int,
    detail: str,
    *,
    errors: list[UnprocessableEntityErrorErrors] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Тело ошибки собирается по модели из контракта.

    Модели ошибок сгенерированы из спеки, поэтому ответ, который здесь
    получится, описан в ней по построению.
    """
    title = HTTPStatus(status_code).phrase
    if errors is None:
        body = ProblemDetails(status=status_code, title=title, detail=detail)
    else:
        body = UnprocessableEntityError(
            status=status_code, title=title, detail=detail, errors=errors
        )

    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json", exclude_none=True, by_alias=True),
        media_type=MEDIA_TYPE,
        headers=headers,
    )


def _describe(error: dict) -> UnprocessableEntityErrorErrors:
    # Первый элемент loc — часть запроса (body, query, path), и в имя
    # поля он не входит: клиент видит его из самой операции.
    location = [str(part) for part in error["loc"][1:]]
    return UnprocessableEntityErrorErrors(
        message=error["msg"],
        rule=error["type"],
        field=".".join(location),
    )


def register_handlers(app: FastAPI) -> None:
    """Все ошибки приложения отдаются в одном формате.

    Фреймворк по умолчанию рисует свои: `{"detail": ...}` у
    HTTPException и `{"detail": [...]}` у проверки запроса. В контракте
    же объявлен один тип тела на все ошибки, и обработчики приводят к
    нему каждый исход.
    """

    # Обработчик объявлен на базовом классе, а не на том, что
    # предлагает fastapi: базовый фреймворк бросает сам — например, 400
    # на нечитаемом теле запроса, — и обработчик, объявленный на
    # наследнике, до такой ошибки не доходит. Она уезжала клиенту в
    # формате по умолчанию, то есть в контракте её тело было описано
    # неверно.
    @app.exception_handler(BaseHTTPException)
    async def http_exception(
        request: Request, error: BaseHTTPException
    ) -> Response:
        return problem_response(
            error.status_code,
            str(error.detail),
            headers=getattr(error, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation(
        request: Request, error: RequestValidationError
    ) -> Response:
        return problem_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "The request does not match the schema of the operation",
            errors=[_describe(item) for item in error.errors()],
        )

    @app.exception_handler(ValidationProblemError)
    async def validation_problem(
        request: Request, error: ValidationProblemError
    ) -> Response:
        return problem_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Errors related to business logic such as uniqueness",
            errors=error.errors,
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, error: Exception) -> Response:
        logger.exception("unhandled error", exc_info=error)
        # Текст ошибки наружу не уходит: он может содержать что угодно,
        # вплоть до фрагмента запроса к базе.
        return problem_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal Server Error"
        )

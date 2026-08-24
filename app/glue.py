from typing import Any, Callable

from fastapi import FastAPI, Response, Security

from app.contract import document

Handlers = dict[str, Callable[..., Any]]
SecurityHandlers = dict[str, Callable[..., Any]]


def _response_model(handler: Callable[..., Any], status: int):
    """Модель ответа операции.

    Берётся из объявления обработчика, а не из документа версии: модель
    там сгенерированная, то есть всё равно порождена контрактом, — а
    обработчики курсов, уроков и токенов общие для обеих версий, потому
    что эти схемы между версиями не менялись. Модель из документа второй
    версии была бы для них другим типом с тем же содержимым, и проверка
    ответа падала бы на ровном месте.

    Расхождение схем, если оно однажды появится, ловят контрактные
    тесты: они сверяют ответ со схемой своей версии.

    У 204 тела нет вовсе, поэтому и модели у него нет.
    """
    model = handler.__annotations__.get("return")
    if status == 204 or model is None or model is Response:
        return None
    return model


def _success_status(operation: dict[str, Any]) -> int:
    return min(
        int(code) for code in operation["responses"] if code.startswith("2")
    )


def register_operations(
    app: FastAPI,
    *,
    version: str,
    handlers: Handlers,
    security_handlers: SecurityHandlers,
    prefix: str = "",
) -> None:
    """Маршруты приложения регистрируются по спеке.

    Это временная замена серверного плагина hey-api. У TypeScript-версии
    генератора такой плагин есть: он вешает маршруты по контракту и
    типизирует обработчики полным набором операций. У python-генератора
    его пока нет, поэтому регистрация написана здесь — и когда плагин
    выйдет, этот файл удаляется целиком (см. TODO.md).

    Что даёт регистрация по спеке, чего не даёт список маршрутов в коде:

    - забытая операция роняет приложение на старте, а не остаётся 404 до
      первой жалобы;
    - лишняя операция, которой нет в контракте, тоже роняет старт, а не
      живёт в приложении незадокументированной;
    - авторизация берётся из `security` контракта. Пока её звали внутри
      обработчиков, во всех пяти операциях пользователей её забыли, и
      список, чтение, правка и удаление стояли открытыми. Забыть её
      здесь негде: обработчик про неё не знает.
    - код успеха, описание и идентификатор операции тоже приходят из
      контракта, поэтому разойтись с ним не могут.
    """
    operations = {
        operation["operationId"]: (path, method, operation)
        for path, methods in document(version)["paths"].items()
        for method, operation in methods.items()
    }

    missing = sorted(operations.keys() - handlers.keys())
    if missing:
        raise RuntimeError(
            f"{version}: контракт объявляет операции, которых нет в "
            f"обработчиках: {', '.join(missing)}"
        )

    extra = sorted(handlers.keys() - operations.keys())
    if extra:
        raise RuntimeError(
            f"{version}: обработчики объявляют операции, которых нет в "
            f"контракте: {', '.join(extra)}"
        )

    for operation_id, (path, method, operation) in operations.items():
        status = _success_status(operation)
        dependencies = [
            Security(security_handlers[scheme])
            for requirement in operation.get("security", [])
            for scheme in requirement
        ]

        app.add_api_route(
            f"{prefix}{path}",
            handlers[operation_id],
            methods=[method.upper()],
            status_code=status,
            response_model=_response_model(handlers[operation_id], status),
            dependencies=dependencies,
            operation_id=operation_id,
            summary=operation.get("summary"),
            tags=operation.get("tags"),
        )

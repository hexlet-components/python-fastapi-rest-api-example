from fastapi import APIRouter, FastAPI, Response, status
from prometheus_client import (
    CollectorRegistry,
    PlatformCollector,
    ProcessCollector,
)
from prometheus_fastapi_instrumentator import Instrumentator
from sqlmodel import literal, select

from app.dependencies import SessionDep

# Ни /health, ни /metrics не входят в контракт: это не часть API, а то,
# что нужно оркестратору и сборщику метрик. Поэтому и в спеке их нет.
router = APIRouter(include_in_schema=False)


@router.get("/health")
async def health(session: SessionDep, response: Response) -> dict[str, str]:
    """Готовность приложения вместе с базой.

    Проверка базы входит в ответ намеренно: живой процесс с мёртвым
    соединением считался бы здоровым, и оркестратор держал бы его в
    балансировщике.
    """
    try:
        await session.exec(select(literal(1)))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error"}

    return {"status": "ok"}


def setup_metrics(app: FastAPI) -> None:
    # Свой реестр на приложение, а не глобальный по умолчанию: реестр
    # prometheus_client один на процесс, и второй подъём приложения
    # падал бы на «Duplicated timeseries». В бою приложение поднимается
    # раз, а в тестах — на каждый прогон файла.
    registry = CollectorRegistry()
    # Метрики самого процесса: память, время процессора, число
    # дескрипторов. Источник — /proc, поэтому на linux они есть, а на
    # macOS сборщик молча не отдаёт ничего.
    ProcessCollector(registry=registry)
    PlatformCollector(registry=registry)

    Instrumentator(
        registry=registry,
        # Коды группируются в 2xx/4xx/5xx, а метрики считаются по шаблону
        # маршрута: иначе /courses/1 и /courses/2 дают отдельные серии, и
        # их число растёт по числу записей.
        should_group_status_codes=True,
        excluded_handlers=["/metrics", "/health"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

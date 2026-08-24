from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import secure
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html

from app import observability
from app.contract import VERSIONS, document
from app.db.session import (
    create_engine,
    create_session_factory,
    migrate,
)
from app.glue import register_operations
from app.lib.problems import register_handlers
from app.middleware import ETagMiddleware, RateLimitMiddleware
from app.routers import index as v1
from app.routers.v2 import index as v2
from app.security import Unauthorized, current_user_id, unauthorized_handler
from app.settings import Settings, get_settings
from app.telemetry import setup_telemetry

TITLE = "Rest API Example"

# Заголовки безопасности одним объявлением, а не набором строк по
# коду. Двух из готового набора здесь нет намеренно:
#
# HSTS — потому что пример запускается по http, и обещание «только
# https» в такой установке ломает доступ к нему же;
# CSP — потому что страница документации грузит свои файлы со стороннего
# адреса и рисует инлайновыми стилями, а политика по умолчанию разрешает
# только собственный источник.
SECURITY_HEADERS = secure.Secure(
    coop=secure.CrossOriginOpenerPolicy().same_origin(),
    permissions=secure.PermissionsPolicy().geolocation().microphone().camera(),
    referrer=secure.ReferrerPolicy().strict_origin_when_cross_origin(),
    server=secure.Server().set(""),
    xcto=secure.XContentTypeOptions().nosniff(),
    xfo=secure.XFrameOptions().deny(),
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    engine = create_engine(settings)
    await migrate(engine)

    factory = create_session_factory(engine)
    app.state.engine = engine
    app.state.session_factory = factory

    if settings.environment != "production":
        # Импорт внутри условия, а не наверху файла: сиды тянут faker из
        # группы dev, которой в боевой установке нет. Со статическим
        # импортом приложение там не поднялось бы вовсе, а поднявшись —
        # завело бы в базе выдуманных пользователей.
        from app.db.seeds import seed

        await seed(factory)

    yield

    await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Сборка приложения.

    Фабрика, а не модульный объект: конфиг передаётся аргументом,
    поэтому тесты поднимают приложение с нужными значениями, не правя
    окружение процесса.
    """
    settings = settings or get_settings()

    app = FastAPI(
        title=TITLE,
        lifespan=lifespan,
        # Ни спека, ни страница документации фреймворком не отдаются:
        # и то и другое берётся из файлов контракта.
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings

    register_handlers(app)
    app.add_exception_handler(Unauthorized, unauthorized_handler)

    app.add_middleware(RateLimitMiddleware, rate_limit=settings.rate_limit)
    app.add_middleware(ETagMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        await SECURITY_HEADERS.set_headers_async(response)
        return response

    # Маршруты вешает регистратор по контракту, а не include_router по
    # списку в коде: обработчики связываются с операциями по
    # идентификатору, и забытая операция роняет старт.
    #
    # Авторизация приходит оттуда же: обработчик про неё не знает, а
    # схема берётся из `security` контракта по имени.
    security_handlers = {"BearerAuth": current_user_id}
    for version, handlers in (("v1", v1.handlers), ("v2", v2.handlers)):
        register_operations(
            app,
            version=version,
            handlers=handlers,
            security_handlers=security_handlers,
            prefix=VERSIONS[version],
        )

    app.include_router(observability.router)
    observability.setup_metrics(app)
    setup_telemetry(app, settings)

    _add_documents(app)

    return app


def _add_documents(app: FastAPI) -> None:
    """Спека и страница документации на каждую версию.

    Отдаётся файл контракта, а не документ, собранный по коду: контракт
    первичен, из него же сгенерированы модели, которыми обработчики
    пользуются. Собранная по коду спека расходилась бы с контрактом
    ровно там, где расходится реализация, и это расхождение уезжало бы
    клиенту под видом контракта.

    Сверку реализации с контрактом ведут две проверки:
    `make contract-check` статически сличает таблицу маршрутов, а
    `make contract-test` бьёт запросами по поднятому приложению.
    """

    for version, prefix in VERSIONS.items():

        @app.get(f"{prefix}/openapi.json", include_in_schema=False)
        async def openapi(version: str = version) -> dict:
            return document(version)

        @app.get(f"{prefix}/docs", include_in_schema=False)
        async def docs(
            prefix: str = prefix, version: str = version
        ) -> Response:
            return get_swagger_ui_html(
                openapi_url=f"{prefix}/openapi.json",
                title=f"{TITLE} — {version}",
            )


app = create_app()

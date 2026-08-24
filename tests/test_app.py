import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.main import create_app
from app.settings import get_settings

ROOT = Path(__file__).resolve().parents[1]

# Всё, что не привязано к одному маршруту: старт приложения, документы,
# формат ошибок и операционные адреса.


@pytest.fixture
def clean_settings():
    # Конфиг читается один раз на процесс, поэтому для проверок старта
    # кеш сбрасывается до и после теста.
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_app_refuses_to_boot_without_a_secret(monkeypatch, clean_settings):
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="jwt_secret"):
        create_app()


def test_app_refuses_to_boot_with_a_short_secret(monkeypatch, clean_settings):
    monkeypatch.setenv("JWT_SECRET", "short")

    with pytest.raises(ValidationError, match="jwt_secret"):
        create_app()


async def test_openapi_document_and_reference_page_are_served(client):
    document = await client.get("/openapi.json")
    assert document.status_code == 200
    assert document.json()["openapi"].startswith("3.")

    page = await client.get("/docs")
    assert page.status_code == 200
    assert "/openapi.json" in page.text


async def test_the_served_document_is_the_contract_itself(client):
    """Клиенту уходит файл контракта, а не пересказ кода.

    Из этого же файла сгенерированы модели, которыми пользуются
    обработчики, поэтому документ и реализация опираются на один
    источник. Собранная по коду спека расходилась бы с контрактом ровно
    там, где расходится реализация.
    """
    served = (await client.get("/openapi.json")).json()
    committed = json.loads((ROOT / "openapi" / "openapi.v1.json").read_text())

    assert served == committed


async def test_both_versions_serve_their_own_document(client):
    v1 = (await client.get("/openapi.json")).json()
    v2 = (await client.get("/v2/openapi.json")).json()

    assert "phone" not in v1["components"]["schemas"]["User"]["properties"]
    assert "phone" in v2["components"]["schemas"]["User"]["properties"]

    # Пути у версий одинаковые: префикс — это выбор развёртывания, а не
    # часть контракта. Адрес версии приходит в servers, и без него
    # клиент, собранный по документу второй версии, стучался бы в
    # корень, то есть в первую.
    assert v1["paths"].keys() == v2["paths"].keys()
    assert v2["servers"] == [{"url": "/v2", "description": "v2"}]
    assert "servers" not in v1 or v1["servers"] != v2["servers"]


async def test_operational_endpoints_stay_out_of_the_contract(client):
    document = (await client.get("/openapi.json")).json()

    assert "/health" not in document["paths"]
    assert "/metrics" not in document["paths"]


async def test_errors_are_rendered_as_problem_details(client, auth_header):
    res = await client.get("/users/999999", headers=auth_header(1))

    assert res.status_code == 404
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json() == {
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
    }


async def test_request_validation_reports_the_field(client):
    res = await client.get("/courses", params={"page": 0})

    assert res.status_code == 422, res.text
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["status"] == 422
    assert [error["field"] for error in body["errors"]] == ["page"]


async def test_repeated_read_with_the_same_tag_returns_304(client):
    first = await client.get("/courses")
    assert first.status_code == 200
    tag = first.headers["etag"]

    second = await client.get("/courses", headers={"If-None-Match": tag})
    assert second.status_code == 304
    assert second.content == b""


async def test_health_reports_the_app_and_its_database(client):
    res = await client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_metrics_are_exposed_in_prometheus_format(client):
    # Запрос до снятия метрик, чтобы серия по маршрутам была непустой.
    await client.get("/courses")

    res = await client.get("/metrics")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/plain")
    assert "http_request_duration_seconds" in res.text
    # Метрики самого процесса проверяются по python_info: счётчики из
    # ProcessCollector читаются из /proc и на linux есть, а на macOS
    # такого источника нет, и тест падал бы от системы разработчика.
    assert "python_info" in res.text


async def test_an_unreadable_body_is_rejected_in_the_same_format(
    client, auth_header, user
):
    """Ошибка фреймворка тоже отдаётся как problem+json.

    Тело, которое не разобрать, останавливает запрос ещё до проверки по
    схеме — эту ошибку бросает сам фреймворк. Обработчик объявлен на
    базовом классе исключения именно поэтому: иначе такой ответ уходил
    клиенту в другом формате, и в контракте он был описан неверно.
    """
    res = await client.post(
        "/courses",
        headers={**auth_header(user.id), "content-type": "application/json"},
        content=b"\x1es\x8fN\x9f\n",
    )

    assert res.status_code == 400, res.text
    assert res.headers["content-type"].startswith("application/problem+json")
    assert res.json()["status"] == 400


async def test_an_out_of_range_identifier_is_rejected(client):
    """Идентификатор ограничен сверху, а не только снизу.

    Без верхней границы такой адрес проходит проверку, доезжает до базы
    и падает там на переполнении: снаружи это 500 на корректном с виду
    запросе. Нашёл контрактный прогон.
    """
    res = await client.get("/courses/5790491620288948600832")

    assert res.status_code == 422, res.text


async def test_an_out_of_range_page_is_rejected(client):
    """Номер страницы ограничен сверху.

    Иначе он уезжает в смещение, которое база не может представить, и
    запрос отдаёт 500. Нашёл контрактный прогон.
    """
    res = await client.get("/courses", params={"page": 10**30})

    assert res.status_code == 422, res.text


async def test_too_many_requests_are_rejected_in_the_same_format():
    """Ограничитель частоты и его ответ.

    Приложению нужен свой экземпляр с низким потолком: у общего он
    задран, иначе тесты, шлющие много запросов, начали бы ловить 429.
    Проверяется и формат тела: 429 объявлен в контракте у каждой
    операции, значит и приходить он должен как problem+json.
    """
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app
    from app.settings import Settings

    app = create_app(Settings(rate_limit="2/minute"))
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            statuses = [
                (await client.get("/courses")).status_code for _ in range(4)
            ]
            last = await client.get("/courses")

    assert statuses[0] == 200
    assert 429 in statuses
    assert last.headers["content-type"].startswith("application/problem+json")
    assert last.json()["status"] == 429


def test_a_forgotten_operation_stops_the_app(monkeypatch):
    """Операция контракта без обработчика роняет старт.

    Маршруты вешает регистратор по спеке, поэтому забыть операцию можно
    только один раз: приложение не поднимется. Пока маршруты
    перечислялись в коде, забытая операция оставалась бы 404 до первой
    жалобы.
    """
    from app.routers import index

    handlers = {
        name: handler
        for name, handler in index.handlers.items()
        if name != "tokensCreate"
    }
    monkeypatch.setattr(index, "handlers", handlers)

    with pytest.raises(RuntimeError, match="tokensCreate"):
        create_app()


def test_an_operation_outside_the_contract_stops_the_app(monkeypatch):
    """Обработчик без операции в контракте роняет старт так же.

    Иначе приложение отвечало бы по адресу, которого в контракте нет, и
    клиент узнавал бы о нём из чужих слов.
    """
    from app.routers import index

    extra = {**index.handlers, "usersArchive": index.handlers["usersShow"]}
    monkeypatch.setattr(index, "handlers", extra)

    with pytest.raises(RuntimeError, match="usersArchive"):
        create_app()

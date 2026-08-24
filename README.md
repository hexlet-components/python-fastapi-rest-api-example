# python-fastapi-rest-api-example

[![Python CI](https://github.com/hexlet-components/python-fastapi-rest-api-example/actions/workflows/python-ci.yml/badge.svg)](https://github.com/hexlet-components/python-fastapi-rest-api-example/actions/workflows/python-ci.yml)

REST API на [FastAPI](https://fastapi.tiangolo.com/), собранный
«по-взрослому»: схема API описана отдельно от кода, база через ORM,
проверка входа по схеме.

## Зачем это нужно

Пример того, как выглядит API-проект, когда он перерастает один файл с
маршрутами:

- **Контракт первичен.** API описан на [TypeSpec](https://typespec.io/) в
  `main.tsp`, из него компилируется OpenAPI, а из OpenAPI —
  pydantic-модели ([hey-api](https://heyapi.dev/)). Приложение отдаёт
  клиенту тот же файл контракта, из которого сгенерированы его модели,
  поэтому документация не расходится с реализацией.
  `make generate-check` в CI не даёт сгенерированному разойтись со
  спекой.
- **Маршруты регистрируются по спеке.** Обработчики связываются с
  операциями контракта по идентификатору (`app/glue.py`), поэтому
  забытая операция роняет приложение на старте, лишняя — тоже, а код
  успеха, описание и авторизация приходят из контракта.
- **База через [SQLModel](https://sqlmodel.tiangolo.com/)**: модели в
  `app/db/models.py`, история схемы — миграции
  [Alembic](https://alembic.sqlalchemy.org/) в `migrations/`. Приложение
  прогоняет их на старте, а `make migration-check` показывает, что модели
  не менялись без миграции. По умолчанию под ними sqlite в памяти
  процесса: отдельного сервиса для запуска примера не нужно, постоянное
  хранение задаётся `DATABASE_URL`.
- **Проверка входа двумя слоями.** Структуру запроса проверяет
  сгенерированная из контракта схема. Правила, для которых нужна база —
  уникальность адреса, — живут отдельным слоем в `app/validators/`, а не
  внутри обработчика.
- **Авторизация берётся из контракта**, а не пишется в обработчиках:
  схема из `security` операции применяется при регистрации маршрута.
  Пока её звали внутри обработчиков, во всех пяти операциях
  пользователей её забыли, и список, чтение, правка и удаление стояли
  открытыми. Забыть её теперь негде: обработчик про неё не знает.
- **Права отдельно от аутентификации.** Токен сообщает, кто пришёл;
  распоряжаться курсом может его автор, и это правило вынесено в
  `app/policies.py`.
- **Одно тело у всех ошибок** —
  [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457.html),
  `application/problem+json`. Модели ошибок тоже сгенерированы из
  контракта, поэтому ответ описан в нём по построению.
- **Условные запросы.** Чтение отдаёт метку версии, повторное чтение с
  `If-None-Match` получает 304, а правка с устаревшим `If-Match`
  отклоняется — иначе два одновременных PUT перезаписывают друг друга.
- **Две версии контракта из одного приложения.** `@added(Versions.v2)` в
  TypeSpec — и вторая версия получает поле, которого нет в первой; каждая
  отдаётся своим документом, из каждого сгенерирован свой набор моделей,
  и обе проверяются контрактными тестами отдельно.
- **Спека проверяется снаружи.** `make contract-test` натравливает
  [schemathesis](https://schemathesis.readthedocs.io/) на поднятое
  приложение: тот генерирует запросы из спеки и ловит то, чего не видят
  ни тесты, ни проверка запросов. Так здесь нашлись 500 на переполнении
  идентификатора, 500 на `null` в необязательном поле и ошибка
  фреймворка, уходившая клиенту в чужом формате.
- **Частота запросов ограничена**, и 429 объявлен в контракте у каждой
  операции. Счётчик живёт в `app/middleware.py` и считает по адресу
  клиента.
- **Наблюдаемость.** `/health` отвечает вместе с базой, `/metrics` отдаёт
  метрики в формате prometheus, трассировка OpenTelemetry поднимается при
  заданном коллекторе. В контракт эти адреса не входят — это не часть API.

Генератор python-кода у hey-api молодой, и часть работы, которую в
TypeScript-версии он делает сам, здесь пока сделана руками. Что именно и
на что это заменится — в [TODO.md](TODO.md).

## Requirement

- Python 3.14
- Node.js 22 — для инструментов контракта: компилятора TypeSpec и
  генератора моделей. Самому приложению node не нужен.

## Структура

```text
main.tsp              контракт: источник истины для всего остального
openapi/              документы OpenAPI, скомпилированные из контракта
app/types/handlers/   pydantic-модели из OpenAPI, руками не правятся
app/main.py           сборка приложения: слои, версии, регистрация маршрутов
app/glue.py           маршруты по спеке — замена серверного плагина
app/contract.py       чтение документов контракта
app/settings.py       конфиг, проверяемый схемой на старте
app/db/               модели SQLModel, проекции и сиды; миграции в migrations/
app/routers/          обработчики и их отображение на операции контракта
app/validators/       правила предметной области, для которых нужна база
app/rules/            правила уровня базы, например уникальность
app/policies.py       права на запись
app/lib/              пароли, метки версий, страницы, ошибки, правка полей
app/middleware.py     метка версии ответа, условные запросы, лимит частоты
scripts/              contract-test.sh, smoke-test.sh и служебные скрипты
tests/                прогон операций через ASGI, без сетевого сервера
```

## Запуск

```bash
make setup
make dev
make test
```

Документация — на <http://localhost:8000/docs>, спека — на `/openapi.json`.
Вторая версия — `/v2/docs` и `/v2/openapi.json`.

Полезное:

```bash
make routes             # таблица маршрутов с объявленной авторизацией
make generate-types     # спека из контракта и модели из спеки
make generate-check     # сгенерированное закоммичено и совпадает с контрактом
make contract-test      # schemathesis по спеке
make lint-openapi       # линт контракта
make migration-generate M="описание"  # миграция по изменённым моделям
make migration-check    # модели не менялись без миграции
make test-coverage      # тесты с порогом покрытия
make smoke-test         # собрать образ и проверить его (нужен docker)
```

---

[![Hexlet Ltd. logo](https://raw.githubusercontent.com/Hexlet/assets/master/images/hexlet_logo128.png)](https://hexlet.io/?utm_source=github&utm_medium=link&utm_campaign=python-fastapi-rest-api-example)

This repository is created and maintained by the team and the community of Hexlet, an educational project. [Read more about Hexlet](https://hexlet.io/?utm_source=github&utm_medium=link&utm_campaign=python-fastapi-rest-api-example).

See most active contributors on [hexlet-friends](https://friends.hexlet.io/).

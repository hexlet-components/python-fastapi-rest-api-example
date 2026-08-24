PORT ?= 8000

install:
	uv sync
	npm ci

# Первичная настройка: зависимости и .env из шаблона.
setup: install env

# cp -n не затирает существующий .env. Значения в шаблоне рабочие: для
# разработки и тестов вписывать ничего не надо.
env:
	cp -n .env.example .env || true

dev:
	uv run fastapi dev app/main.py --port $(PORT)

start:
	uv run fastapi run app/main.py --port $(PORT)

test:
	uv run pytest

# Пороги покрытия чуть ниже фактических: гейт нужен как храповик против
# регресса, а не как повод подгонять цифры. Сгенерированное из контракта
# в счёт не идёт — покрытие должно говорить о коде, который писали
# руками.
test-coverage:
	uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=93

lint:
	uv run ruff check .
	uv run ruff format --check .
	$(MAKE) lint-openapi

lint-fix:
	uv run ruff check --fix .
	uv run ruff format .

# Таблица маршрутов: операции берутся из контракта, поэтому в ней видно и
# объявленную авторизацию.
routes:
	uv run python -m scripts.routes

# Спека из контракта. Источник истины — main.tsp, документы OpenAPI это
# порождённый из него артефакт, который коммитится: по нему генерируются
# модели, его же отдаёт приложение и по нему идут контрактные тесты.
generate-openapi:
	npx tsp compile .

# Модели из спеки. Путь начинается с ./ намеренно: без этого генератор
# принимает его за адрес проекта в реестре Hey API и падает на разборе.
generate-models:
	npx openapi-python -i ./openapi/openapi.v1.json -o ./app/types/handlers/v1 -p pydantic
	npx openapi-python -i ./openapi/openapi.v2.json -o ./app/types/handlers/v2 -p pydantic

generate-types: generate-openapi generate-models

# Проверка, что сгенерированное закоммичено: перегенерируем и падаем,
# если рабочее дерево изменилось. Ловит и забытый коммит, и сломанный
# генератор — без этой цели поломка видна только тому, кто запустит
# генерацию руками.
generate-check: generate-types
	@git diff --exit-code -- openapi app/types/handlers || { \
		echo "Сгенерированное разошлось с контрактом — запустите make generate-types"; \
		exit 1; \
	}

# Линт контракта: разбор настоящим валидатором OpenAPI плюс свои правила.
# Гоняется по сгенерированному документу, а не по main.tsp: проверять
# надо то, что видит клиент.
lint-openapi:
	uv run python -m scripts.openapi_lint

migration-generate:
	uv run alembic revision --autogenerate -m "$(M)"
	uv run ruff check --fix migrations
	uv run ruff format migrations

# Схема без миграции — молчаливая поломка: код ждёт колонку, которой в
# базе не появится. Цель накатывает миграции на временную базу и
# спрашивает alembic, осталось ли расхождение с моделями.
#
# База именно файловая: alembic check открывает своё соединение, а база
# в памяти существует только внутри того соединения, которое её создало.
migration-check:
	@rm -f .migration-check.sqlite
	DATABASE_URL=sqlite:///.migration-check.sqlite uv run alembic upgrade head
	DATABASE_URL=sqlite:///.migration-check.sqlite uv run alembic check
	@rm -f .migration-check.sqlite

# Контрактные тесты поверх спеки: см. комментарий в самом скрипте.
contract-test:
	./scripts/contract-test.sh

# Проверка собранного образа: см. комментарий в самом скрипте.
smoke-test:
	./scripts/smoke-test.sh

# Обычно обновления приносит dependabot — цель нужна, когда хочется
# обновиться сразу и локально.
deps-update:
	uv lock --upgrade
	npx npm-check-updates -u

.PHONY: install setup env dev start test test-coverage lint lint-fix routes \
	generate-openapi generate-models generate-types generate-check \
	lint-openapi migration-generate migration-check contract-test \
	smoke-test deps-update

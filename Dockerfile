# Сборки как отдельного шага нет: питон исполняет исходники, собирать
# нечего. Образ ставит зависимости из локфайла и копирует код.
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS deps

WORKDIR /app

# Сначала только манифест и локфайл: слой с зависимостями не
# пересобирается при каждой правке кода.
COPY pyproject.toml uv.lock ./
# --no-dev: боевой установке не нужны ни pytest, ни faker. Это не
# экономия места, а требование — сиды тянут faker, и без этой границы
# фикстуры доехали бы до боя.
# --frozen: локфайл не пересчитывается, иначе версии в образе разъедутся
# с проверенными в CI.
RUN uv sync --frozen --no-dev --no-install-project

FROM python:3.14-slim AS runtime

ENV ENVIRONMENT=production \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Непривилегированный пользователь: процесс приложения не должен уметь
# писать в собственный код.
RUN useradd --create-home --uid 1000 api
USER api

COPY --chown=api:api --from=deps /app/.venv ./.venv
COPY --chown=api:api alembic.ini ./
COPY --chown=api:api migrations ./migrations
# Контракт нужен в бою: приложение отдаёт его клиенту и читает из него
# правила, которые сгенерированные модели не выражают.
COPY --chown=api:api openapi ./openapi
COPY --chown=api:api app ./app

EXPOSE 8000

# Один процесс: масштабирование — забота того, кто запускает контейнер, а
# не образа. Миграции приложение прогоняет само на старте.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

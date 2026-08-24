import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env не читается в тестах: иначе прогон начинает зависеть от локального
# файла разработчика, а проверка «без секрета приложение не поднимается»
# ломается — файл подтягивает секрет обратно после удаления переменной.
# В тестах значения приходят из tests/conftest.py.
ENV_FILE = None if os.environ.get("ENVIRONMENT") == "test" else ".env"


class Settings(BaseSettings):
    """Конфиг проверяется схемой на старте.

    Приложение с пустым или коротким JWT_SECRET не поднимается вовсе,
    вместо того чтобы подписывать токены строкой вроде "supersecret".
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    jwt_secret: str = Field(min_length=32)
    # Срок жизни токена. Без него один раз выданный токен работал бы
    # всегда, а отозвать его можно было только удалением пользователя.
    jwt_expires_in: int = 3600
    jwt_algorithm: str = "HS256"

    environment: Literal["development", "test", "production"] = "development"

    # По умолчанию база живёт в памяти процесса и пересоздаётся при каждом
    # старте: отдельного сервиса для запуска примера не нужно. Постоянное
    # хранение — это путь к файлу или адрес postgres в этой переменной.
    database_url: str = "sqlite+aiosqlite://"

    cors_origin: str = "*"

    # Лимит на адрес. В тестах приложение поднимается много раз в одном
    # процессе, поэтому значение вынесено в окружение, а не зашито в код.
    rate_limit: str = "100/minute"

    # Стоимость scrypt. Боевое значение считается сотни миллисекунд, а
    # сиды прогоняются на каждый подъём приложения в тестах, поэтому
    # цена выносится наружу. Внутри дайджеста она хранится своя, так что
    # смена значения не обесценивает выданные хеши.
    scrypt_cost: int = 16384

    # Трассировка включается только при заданном коллекторе.
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "python-fastapi-rest-api-example"


@lru_cache
def get_settings() -> Settings:
    """Конфиг читается один раз на процесс.

    Кеш сбрасывается в тестах (`get_settings.cache_clear()`), где нужно
    проверить, что приложение с плохим секретом не поднимается.
    """
    return Settings()

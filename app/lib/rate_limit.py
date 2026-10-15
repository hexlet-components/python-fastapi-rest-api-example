from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.lib.problems import TooManyRequests, to_response
from app.settings import Settings


def create_limiter(settings: Settings) -> Limiter:
    """Ограничитель частоты запросов на адрес клиента.

    Адрес берётся из соединения, а не из заголовка X-Forwarded-For:
    заголовок присылает клиент, и по нему лимит обходится подстановкой
    чужого адреса. За прокси доверять можно только тому заголовку,
    который прокси сам и перезаписывает.

    Счётчик по умолчанию живёт в памяти процесса, то есть считает по
    экземпляру. За несколькими экземплярами в `RATE_LIMIT_STORAGE`
    указывается redis. Клиент хранилища у slowapi синхронный, поэтому
    для redis это блокирующий вызов в цикле событий; память от этого
    свободна.
    """
    return Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit],
        storage_uri=settings.rate_limit_storage,
    )


def too_many_requests(request: Request, error: Exception) -> Response:
    """429 в формате остальных ошибок.

    Готовый обработчик slowapi отдаёт `{"error": ...}`, а в контракте
    429 объявлен как problem+json у каждой операции.
    """
    assert isinstance(error, RateLimitExceeded)  # noqa: S101
    window = error.limit.limit.get_expiry() if error.limit else 0
    return to_response(
        TooManyRequests(
            f"Rate limit exceeded: {error.detail}",
            headers={"Retry-After": str(window)},
        )
    )

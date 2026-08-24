import hashlib
import time

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.lib.problems import problem_response

CACHEABLE_METHODS = ("GET", "HEAD")


class ETagMiddleware:
    """Метка версии ответа и условные запросы.

    Считает ETag по телу ответа и сам отдаёт 304, если клиент прислал
    If-None-Match с тем же значением: повторное чтение не тратит канал на
    те же байты. Уже выставленный обработчиком заголовок не
    перезаписывается — этим пользуются курсы, где метка строится из
    updated_at, чтобы её можно было сверить с If-Match, не пересобирая
    тело байт в байт.

    Промежуточный слой написан на голом ASGI, а не поверх готового
    BaseHTTPMiddleware: тело нужно целиком, до отправки, и удобнее
    собрать его из сообщений самому. Ответ при этом буферизуется, так
    что слой годится для JSON-ответов и не годится для потоковых.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http" or scope["method"] not in CACHEABLE_METHODS:
            await self.app(scope, receive, send)
            return

        if_none_match = Headers(scope=scope).get("if-none-match")
        start: Message | None = None
        chunks: list[bytes] = []

        async def collect(message: Message) -> None:
            nonlocal start

            if message["type"] == "http.response.start":
                start = message
                return

            if message["type"] != "http.response.body":
                await send(message)
                return

            chunks.append(message.get("body", b""))
            if message.get("more_body", False):
                return

            await self._finish(start, b"".join(chunks), if_none_match, send)

        await self.app(scope, receive, collect)

    async def _finish(
        self,
        start: Message | None,
        body: bytes,
        if_none_match: str | None,
        send: Send,
    ) -> None:
        if start is None:
            return

        headers = MutableHeaders(scope=start)
        if start["status"] == 200 and body:
            etag = headers.get("etag") or self._weak_tag(body)
            headers["etag"] = etag

            if if_none_match is not None and etag in [
                value.strip() for value in if_none_match.split(",")
            ]:
                del headers["content-length"]
                start = {**start, "status": 304}
                await send(start)
                await send({"type": "http.response.body", "body": b""})
                return

        await send(start)
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _weak_tag(body: bytes) -> str:
        # Валидатор слабый: сравнение идёт по содержимому ответа, а не по
        # точному представлению, и заголовки в него не входят.
        return f'W/"{hashlib.sha1(body).hexdigest()}"'


WINDOWS = {"second": 1, "minute": 60, "hour": 3600}


def parse_rate_limit(value: str) -> tuple[int, int]:
    """Лимит из конфига: «<число>/<единица времени>»."""
    limit, _, unit = value.partition("/")
    if unit not in WINDOWS:
        raise ValueError(
            f"лимит задаётся как 100/minute, единицы: "
            f"{', '.join(WINDOWS)}; получено {value!r}"
        )
    return int(limit), WINDOWS[unit]


class RateLimitMiddleware:
    """Ограничитель частоты запросов на адрес клиента.

    Окно фиксированное: счётчик на адрес обнуляется, когда окно
    закончилось. Готовая библиотека сюда не годится — общий для всех
    маршрутов ограничитель ищет обработчик по списку маршрутов
    приложения, а fastapi с некоторых версий хранит там ссылки на
    роутеры, а не сами операции. Ограничитель молча пропускал всё, и
    объявленный в контракте 429 не наступал никогда.

    Счётчик живёт в памяти процесса, то есть считает по экземпляру. За
    несколькими экземплярами нужен общий счётчик — redis или сам
    балансировщик.
    """

    def __init__(self, app: ASGIApp, *, rate_limit: str) -> None:
        self.app = app
        self.limit, self.window = parse_rate_limit(rate_limit)
        self.counters: dict[str, tuple[float, int]] = {}

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Адрес берётся из соединения, а не из заголовка
        # X-Forwarded-For: заголовок присылает клиент, и по нему лимит
        # обходится подстановкой чужого адреса. За прокси доверять можно
        # только тому заголовку, который прокси сам и перезаписывает.
        client = scope.get("client")
        key = client[0] if client else "unknown"

        if self._exceeded(key):
            response = problem_response(
                429,
                f"Rate limit exceeded: {self.limit} per {self.window} s",
                headers={"Retry-After": str(self.window)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _exceeded(self, key: str) -> bool:
        now = time.monotonic()
        started, count = self.counters.get(key, (now, 0))

        if now - started >= self.window:
            started, count = now, 0

        self.counters[key] = (started, count + 1)
        self._forget_stale(now)

        return count >= self.limit

    def _forget_stale(self, now: float) -> None:
        # Ключей столько же, сколько адресов, и без уборки словарь растёт
        # всё время работы процесса. Порог, а не проход на каждый запрос:
        # уборка стоит обхода всего словаря.
        if len(self.counters) < 1000:
            return

        self.counters = {
            key: value
            for key, value in self.counters.items()
            if now - value[0] < self.window
        }

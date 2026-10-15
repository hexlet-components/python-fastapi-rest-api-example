import hashlib

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
        return f'W/"{hashlib.sha1(body, usedforsecurity=False).hexdigest()}"'

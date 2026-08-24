from datetime import datetime

from app.lib.problems import PreconditionFailed


def entity_tag(updated_at: datetime) -> str:
    """Метка версии записи.

    Считается из updated_at, а не из тела ответа: тело пришлось бы
    пересобирать байт в байт, чтобы сверить с присланным If-Match.
    Валидатор слабый (W/) — сравнение идёт по версии записи, а не по
    точному представлению.
    """
    return f'W/"{int(updated_at.timestamp() * 1000)}"'


def ensure_matches(if_match: str | None, updated_at: datetime) -> None:
    """Проверка условия правки.

    Заголовок необязателен: без него правка проходит как обычно. Но если
    клиент его прислал, а запись с тех пор изменилась, правка
    отклоняется — иначе два одновременных PUT молча перезаписывают друг
    друга, и переживает тот, кто пришёл вторым.
    """
    if if_match is None:
        return

    current = entity_tag(updated_at)
    candidates = [value.strip() for value in if_match.split(",")]
    if "*" in candidates or current in candidates:
        return

    raise PreconditionFailed("The resource has changed since it was fetched")

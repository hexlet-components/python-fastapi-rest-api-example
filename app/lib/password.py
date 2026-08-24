import asyncio
import hashlib
import hmac
import secrets

SALT_BYTES = 16
KEY_LENGTH = 64
BLOCK_SIZE = 8
PARALLELISM = 1


def _memory_for(cost: int) -> int:
    """scrypt требует памяти порядка 128 * N * r.

    Лимит считается от стоимости: дефолта OpenSSL хватает не на любое
    значение, и на большом N вызов падает с «memory limit exceeded».
    """
    return 128 * cost * BLOCK_SIZE * 2


def _derive(password: str, salt: str, cost: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode(),
        salt=salt.encode(),
        n=cost,
        r=BLOCK_SIZE,
        p=PARALLELISM,
        maxmem=_memory_for(cost),
        dklen=length,
    )


async def hash_password(password: str, cost: int) -> str:
    """Хеш пароля со стоимостью внутри дайджеста.

    Стоимость хранится рядом с хешем, а не берётся из конфига при
    проверке: иначе смена настройки разом обесценивает все выданные
    хеши.

    Счёт идёт в отдельном потоке: scrypt держит процессор десятки
    миллисекунд и остановил бы весь событийный цикл, а не один запрос.
    """
    salt = secrets.token_hex(SALT_BYTES)
    derived = await asyncio.to_thread(_derive, password, salt, cost, KEY_LENGTH)
    return f"scrypt${cost}${salt}${derived.hex()}"


async def verify_password(password: str, digest: str) -> bool:
    parts = digest.split("$")
    if len(parts) != 4:
        return False

    scheme, raw_cost, salt, key = parts
    if scheme != "scrypt" or not raw_cost.isdigit() or not salt or not key:
        return False

    cost = int(raw_cost)
    if cost < 2:
        return False

    expected = bytes.fromhex(key)
    derived = await asyncio.to_thread(
        _derive, password, salt, cost, len(expected)
    )
    # Сравнение за постоянное время: обычное == утекает длину общего
    # префикса, а по ней подбирается хеш побайтово.
    return hmac.compare_digest(expected, derived)

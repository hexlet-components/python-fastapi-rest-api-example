import os

# Окружение задаётся до импорта приложения: конфиг читается схемой на
# старте, а .env в тестах не читается вовсе — иначе прогон зависел бы от
# локального файла разработчика.
os.environ["ENVIRONMENT"] = "test"
# Схема требует секрет от 32 символов, и это правильно: приложение не
# должно подниматься с пустым. Тестам он нужен любой.
os.environ.setdefault(
    "JWT_SECRET", "test-secret-not-used-anywhere-else-0123456789"
)
# Боевая цена scrypt — сотни миллисекунд на хеш, а сиды прогоняются на
# каждый подъём приложения. Стоимость лежит внутри дайджеста, так что
# проверка пароля от этого не ломается.
os.environ.setdefault("SCRYPT_COST", "1024")
# Ограничитель частоты живёт в памяти приложения, но потолок лучше
# задрать: иначе тест, шлющий много запросов, начинает ловить 429.
os.environ.setdefault("RATE_LIMIT", "100000/minute")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.db.models import Course, CourseLesson, User  # noqa: E402
from app.lib.data import DEFAULT_PASSWORD  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security import create_token  # noqa: E402
from app.settings import Settings  # noqa: E402

MISSING_ID = 999_999


@pytest.fixture
async def app():
    """Приложение с базой в памяти на каждый тест.

    Каждый тест получает свою базу: обработчики меняют данные, и общая
    база делала бы результат зависимым от порядка прогона. Подъём стоит
    дёшево — миграции по трём таблицам и три пользователя в сидах.
    """
    instance = create_app(Settings())
    async with instance.router.lifespan_context(instance):
        yield instance


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        yield client


@pytest.fixture
async def session(app):
    """Сессия для проверок в самих тестах.

    Тест смотрит на состояние базы своей сессией, а не той, что была у
    запроса: иначе он проверял бы объекты, оставшиеся в памяти
    обработчика, а не то, что уехало в базу.
    """
    async with app.state.session_factory() as session:
        yield session


async def first(session, model):
    # Порядок задан явно: без него база его не обещает, и «первая»
    # запись до правки и после — не обязательно одна и та же.
    return await session.scalar(select(model).order_by(model.id).limit(1))


@pytest.fixture
async def user(session) -> User:
    return await first(session, User)


@pytest.fixture
async def course(session) -> Course:
    return await first(session, Course)


@pytest.fixture
async def lesson(session) -> CourseLesson:
    return await first(session, CourseLesson)


@pytest.fixture
def refetch(session):
    """Запись из базы заново, поверх того, что лежит в сессии.

    Сессия помнит объекты, которые уже читала, поэтому без
    populate_existing тест увидел бы состояние до запроса, а не после.
    Удалённая запись при этом возвращается как None, а не ошибкой.
    """

    async def find(model, model_id: int):
        return await session.scalar(
            select(model)
            .where(model.id == model_id)
            .execution_options(populate_existing=True)
        )

    return find


@pytest.fixture
def auth_header(app):
    """Заголовок с токеном произвольного пользователя."""

    def build(user_id: int) -> dict[str, str]:
        token = create_token(user_id, app.state.settings)
        return {"Authorization": f"Bearer {token}"}

    return build


@pytest.fixture
async def outsider(session):
    """Пользователь, который эту запись не создавал.

    Владение проверяется отдельно от аутентификации, и токеном «просто
    вошедшего» его не подменить.
    """

    async def find(owner_id: int) -> User:
        users = (await session.scalars(select(User).order_by(User.id))).all()
        return next(user for user in users if user.id != owner_id)

    return find


@pytest.fixture
def password() -> str:
    return DEFAULT_PASSWORD

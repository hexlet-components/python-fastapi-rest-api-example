from faker import Faker

from app.lib.password import hash_password

fake = Faker()

# Пароль у всех тестовых пользователей один: тестам нужно уметь
# получать токен под любым из них, а перебирать значения незачем.
DEFAULT_PASSWORD = "correct-horse-battery-staple"

# Стоимость scrypt для фикстур. Боевая цена — сотни миллисекунд на хеш,
# и платить её за каждого выдуманного пользователя не за что.
FIXTURE_SCRYPT_COST = 1024


def build_user(**params) -> dict:
    """Форма запроса к API: с открытым паролем."""
    user = {
        "full_name": fake.name(),
        "email": fake.unique.email().lower(),
        "password": DEFAULT_PASSWORD,
        # В контракте поле появляется только со второй версии, но в базе
        # есть всегда: колонка nullable.
        "phone": fake.numerify("+7##########"),
    }
    return {**user, **params}


async def build_user_record(**params) -> dict:
    """Форма строки в базе: с хешем вместо пароля.

    Нужна сидам и тестам, которые заводят пользователя напрямую, минуя
    операцию регистрации.
    """
    user = build_user(**params)
    password = user.pop("password")
    digest = await hash_password(password, FIXTURE_SCRYPT_COST)
    return {**user, "password_digest": digest}


def build_course(**params) -> dict:
    course = {
        "name": fake.sentence(nb_words=4),
        "description": fake.paragraph(),
    }
    return {**course, **params}


def build_lesson(**params) -> dict:
    lesson = {
        "name": fake.sentence(nb_words=4),
        "body": fake.paragraph(),
    }
    return {**lesson, **params}

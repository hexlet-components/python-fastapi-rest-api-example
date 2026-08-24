import jwt

from app.db.models import User
from app.lib.data import build_user


async def test_create(client, user, password):
    res = await client.post(
        "/tokens", json={"email": user.email, "password": password}
    )

    assert res.status_code == 201, res.text
    assert res.json()["token"]


async def test_the_token_opens_a_protected_operation(
    client, app, user, password
):
    created = await client.post(
        "/tokens", json={"email": user.email, "password": password}
    )
    token = created.json()["token"]

    res = await client.get(
        "/users", headers={"Authorization": f"Bearer {token}"}
    )

    assert res.status_code == 200, res.text


async def test_the_token_carries_an_expiry(client, app, user, password):
    """Токен выдаётся со сроком жизни.

    Без срока один раз выданный токен работал бы всегда, а отозвать его
    можно было бы только удалением пользователя.
    """
    created = await client.post(
        "/tokens", json={"email": user.email, "password": password}
    )

    payload = jwt.decode(
        created.json()["token"],
        app.state.settings.jwt_secret,
        algorithms=[app.state.settings.jwt_algorithm],
    )

    assert payload["exp"] > 0


async def test_a_wrong_password_and_an_unknown_email_look_alike(client, user):
    """Один ответ на оба случая.

    Иначе операция превращается в проверку того, зарегистрирован ли
    адрес: по разнице ответов её видно снаружи.
    """
    wrong = await client.post(
        "/tokens", json={"email": user.email, "password": "not-the-password"}
    )
    unknown = await client.post(
        "/tokens",
        json={"email": build_user()["email"], "password": "not-the-password"},
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_an_expired_token_is_rejected(client, app, user, session):
    import datetime

    expired = jwt.encode(
        {
            "id": user.id,
            "exp": datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=1),
        },
        app.state.settings.jwt_secret,
        algorithm=app.state.settings.jwt_algorithm,
    )

    res = await client.get(
        "/users", headers={"Authorization": f"Bearer {expired}"}
    )

    assert res.status_code == 401, res.text


async def test_a_token_signed_by_another_secret_is_rejected(client, user):
    forged = jwt.encode(
        {"id": user.id}, "another-secret-entirely-0123456789", algorithm="HS256"
    )

    res = await client.get(
        "/users", headers={"Authorization": f"Bearer {forged}"}
    )

    assert res.status_code == 401, res.text


async def test_the_password_digest_never_leaves_the_database(
    client, auth_header, user, session
):
    """Проекция не отдаёт хеш даже в списке.

    Схема ответа его и так не пропустит, но проекция нужна затем, чтобы
    секрет не покидал базу вовсе — если у маршрута однажды не окажется
    схемы, сериализатор перестанет прикрывать.
    """
    stored = await session.get(User, user.id)
    res = await client.get("/users", headers=auth_header(user.id))

    assert stored.password_digest
    assert stored.password_digest not in res.text

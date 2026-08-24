from app.db.models import User
from app.lib.data import build_user
from app.lib.password import verify_password
from tests.conftest import MISSING_ID


async def test_index(client, auth_header, user):
    res = await client.get("/users", headers=auth_header(user.id))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["meta"]["page"] == 1
    assert body["meta"]["total"] == len(body["data"]) >= 3


async def test_index_paginates(client, auth_header, user):
    res = await client.get(
        "/users", params={"page": 2, "perPage": 2}, headers=auth_header(user.id)
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["meta"] == {
        "page": 2,
        "perPage": 2,
        "total": 3,
        "totalPages": 2,
    }
    assert len(body["data"]) == 1


async def test_show(client, auth_header, user):
    res = await client.get(f"/users/{user.id}", headers=auth_header(user.id))

    assert res.status_code == 200, res.text
    assert res.json() == {
        "id": user.id,
        "fullName": user.full_name,
        "email": user.email,
    }


async def test_show_missing(client, auth_header, user):
    res = await client.get(f"/users/{MISSING_ID}", headers=auth_header(user.id))

    assert res.status_code == 404


async def test_create(client, session, refetch):
    data = build_user()

    res = await client.post(
        "/users",
        json={
            "fullName": data["full_name"],
            "email": data["email"],
            "password": data["password"],
        },
    )

    assert res.status_code == 201, res.text
    body = res.json()
    # Ни пароля, ни хеша в ответе быть не должно: схема ответа
    # перечисляет публичные поля, и всё остальное отбрасывается.
    assert set(body) == {"id", "fullName", "email"}

    created = await refetch(User, body["id"])
    assert created.password_digest != data["password"]
    assert await verify_password(data["password"], created.password_digest)


async def test_create_with_a_taken_email(client, user):
    data = build_user(email=user.email)

    res = await client.post(
        "/users", json={"email": data["email"], "password": data["password"]}
    )

    assert res.status_code == 422, res.text
    body = res.json()
    assert body["errors"] == [
        {
            "message": "email is already taken",
            "rule": "unique",
            "field": "email",
        }
    ]


async def test_create_with_the_same_email_in_another_case(client, user):
    """Адрес в другом регистре — тот же адрес.

    Без приведения к нижнему регистру проверка уникальности его
    пропускает, и в базе оказываются два пользователя с одним ящиком.
    """
    res = await client.post(
        "/users",
        json={"email": user.email.upper(), "password": "long-enough-pass"},
    )

    assert res.status_code == 422, res.text


async def test_create_with_a_short_password(client):
    data = build_user()

    res = await client.post(
        "/users", json={"email": data["email"], "password": "short"}
    )

    assert res.status_code == 422, res.text
    assert [error["field"] for error in res.json()["errors"]] == ["password"]


async def test_replace(client, auth_header, user, refetch):
    res = await client.put(
        f"/users/{user.id}",
        headers=auth_header(user.id),
        json={"fullName": "Новое имя"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["fullName"] == "Новое имя"
    updated = await refetch(User, user.id)
    assert updated.full_name == "Новое имя"
    # Присланное поле меняется, остальные остаются: тело правки может
    # быть неполным, и незаполненное поле не значит «стереть».
    assert updated.email == user.email


async def test_replace_changes_the_password(client, auth_header, user, refetch):
    res = await client.put(
        f"/users/{user.id}",
        headers=auth_header(user.id),
        json={"password": "another-long-password"},
    )

    assert res.status_code == 200, res.text
    updated = await refetch(User, user.id)
    assert await verify_password(
        "another-long-password", updated.password_digest
    )


async def test_replace_with_an_empty_body(client, auth_header, user):
    res = await client.put(
        f"/users/{user.id}", headers=auth_header(user.id), json={}
    )

    # Менять нечего, но и ошибки тут нет: запрос корректен, состояние
    # остаётся прежним.
    assert res.status_code == 200, res.text
    assert res.json()["email"] == user.email


async def test_destroy(client, auth_header, session, refetch):
    # Удаляется пользователь без курсов: у автора курсов удаление
    # отклоняется, и это отдельный тест.
    data = build_user()
    created = await client.post(
        "/users",
        json={"email": data["email"], "password": data["password"]},
    )
    user_id = created.json()["id"]

    res = await client.delete(f"/users/{user_id}", headers=auth_header(user_id))

    assert res.status_code == 204, res.text
    assert await refetch(User, user_id) is None


async def test_destroy_an_author_of_courses(client, auth_header, course):
    res = await client.delete(
        f"/users/{course.creator_id}", headers=auth_header(course.creator_id)
    )

    assert res.status_code == 409, res.text
    assert "course" in res.json()["detail"]


async def test_every_operation_but_registration_needs_a_token(client, user):
    """Регистрация открыта, остальные операции — нет.

    Проверяются все четыре разом: пока авторизацию звали внутри каждого
    обработчика, её забыли сразу во всех, и список, чтение, правка и
    удаление пользователей стояли открытыми.
    """
    requests = [
        client.get("/users"),
        client.get(f"/users/{user.id}"),
        client.put(f"/users/{user.id}", json={"fullName": "Имя"}),
        client.delete(f"/users/{user.id}"),
    ]

    for request in requests:
        res = await request
        assert res.status_code == 401, res.text
        assert res.headers["www-authenticate"] == "Bearer"


async def test_a_token_of_a_deleted_user_is_rejected(
    client, auth_header, session
):
    data = build_user()
    created = await client.post(
        "/users", json={"email": data["email"], "password": data["password"]}
    )
    user_id = created.json()["id"]
    header = auth_header(user_id)
    await client.delete(f"/users/{user_id}", headers=header)

    res = await client.get("/users", headers=header)

    # Токен ещё не истёк, но пользователя больше нет: без проверки
    # запрос шёл бы дальше с идентификатором, которого в базе нет.
    assert res.status_code == 401, res.text


async def test_the_second_version_reads_and_writes_the_phone(
    client, auth_header, user
):
    data = build_user()

    created = await client.post(
        "/v2/users",
        json={
            "email": data["email"],
            "password": data["password"],
            "phone": "+70000000000",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["phone"] == "+70000000000"

    shown = await client.get(
        f"/v2/users/{created.json()['id']}", headers=auth_header(user.id)
    )
    assert shown.json()["phone"] == "+70000000000"


async def test_the_first_version_hides_the_phone(client, auth_header, user):
    # Поле есть в базе у каждого пользователя из сидов, но в контракт
    # первой версии оно не входит — и проекция его не отдаёт.
    res = await client.get(f"/users/{user.id}", headers=auth_header(user.id))

    assert user.phone is not None
    assert "phone" not in res.json()


async def test_the_second_version_lists_the_phone(client, auth_header, user):
    res = await client.get("/v2/users", headers=auth_header(user.id))

    assert res.status_code == 200, res.text
    assert all("phone" in item for item in res.json()["data"])


async def test_the_second_version_replaces_the_phone(
    client, auth_header, user, refetch
):
    res = await client.put(
        f"/v2/users/{user.id}",
        headers=auth_header(user.id),
        json={"phone": "+79990000000"},
    )

    assert res.status_code == 200, res.text
    assert res.json()["phone"] == "+79990000000"
    assert (await refetch(User, user.id)).phone == "+79990000000"


async def test_the_second_version_replace_with_an_empty_body(
    client, auth_header, user
):
    res = await client.put(
        f"/v2/users/{user.id}", headers=auth_header(user.id), json={}
    )

    assert res.status_code == 200, res.text
    assert res.json()["email"] == user.email


async def test_the_second_version_destroys_a_user(client, auth_header, refetch):
    data = build_user()
    created = await client.post(
        "/v2/users",
        json={"email": data["email"], "password": data["password"]},
    )
    user_id = created.json()["id"]

    res = await client.delete(
        f"/v2/users/{user_id}", headers=auth_header(user_id)
    )

    assert res.status_code == 204, res.text
    assert await refetch(User, user_id) is None


async def test_the_second_version_keeps_the_author_of_courses(
    client, auth_header, course
):
    res = await client.delete(
        f"/v2/users/{course.creator_id}",
        headers=auth_header(course.creator_id),
    )

    assert res.status_code == 409, res.text


async def test_the_second_version_shows_a_missing_user(
    client, auth_header, user
):
    res = await client.get(
        f"/v2/users/{MISSING_ID}", headers=auth_header(user.id)
    )

    assert res.status_code == 404

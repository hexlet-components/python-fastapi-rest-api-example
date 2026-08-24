from app.db.models import Course, CourseLesson
from app.lib.data import build_course
from tests.conftest import MISSING_ID


async def test_index(client):
    res = await client.get("/courses")

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["meta"]["total"] == len(body["data"]) == 2


async def test_show(client, course):
    res = await client.get(f"/courses/{course.id}")

    assert res.status_code == 200, res.text
    assert res.json() == {
        "id": course.id,
        "name": course.name,
        "description": course.description,
    }


async def test_show_missing(client):
    res = await client.get(f"/courses/{MISSING_ID}")

    assert res.status_code == 404


async def test_create(client, auth_header, user, refetch):
    data = build_course()

    res = await client.post("/courses", headers=auth_header(user.id), json=data)

    assert res.status_code == 201, res.text
    created = await refetch(Course, res.json()["id"])
    assert created.name == data["name"]
    # Автором становится владелец токена, а не поле из запроса: иначе
    # курс можно создать от чужого имени.
    assert created.creator_id == user.id


async def test_replace(client, auth_header, course, refetch):
    res = await client.put(
        f"/courses/{course.id}",
        headers=auth_header(course.creator_id),
        json={"name": "Переименованный курс"},
    )

    assert res.status_code == 200, res.text
    updated = await refetch(Course, course.id)
    assert updated.name == "Переименованный курс"
    assert updated.description == course.description


async def test_destroy(client, auth_header, course, refetch):
    res = await client.delete(
        f"/courses/{course.id}", headers=auth_header(course.creator_id)
    )

    assert res.status_code == 204, res.text
    assert await refetch(Course, course.id) is None


async def test_destroy_takes_the_lessons_with_it(
    client, auth_header, lesson, refetch
):
    """Уроки удаляются вместе с курсом.

    Урок вне курса не существует, но сносит их обработчик в одной
    транзакции с курсом, а не каскад из миграции: поведение должно быть
    видно в коде и проверено тестом.
    """
    owner = (await refetch(Course, lesson.course_id)).creator_id

    res = await client.delete(
        f"/courses/{lesson.course_id}", headers=auth_header(owner)
    )

    assert res.status_code == 204, res.text
    assert await refetch(CourseLesson, lesson.id) is None


async def test_reading_is_open_and_writing_is_not(client, course):
    requests = [
        client.post("/courses", json=build_course()),
        client.put(f"/courses/{course.id}", json={"name": "Имя"}),
        client.delete(f"/courses/{course.id}"),
    ]

    for request in requests:
        res = await request
        assert res.status_code == 401, res.text

    assert (await client.get("/courses")).status_code == 200
    assert (await client.get(f"/courses/{course.id}")).status_code == 200


async def test_someone_elses_course_is_off_limits(
    client, auth_header, course, outsider
):
    """Токен подтверждает, кто пришёл, а не что ему можно.

    Право на курс — отдельная проверка: без неё любой вошедший меняет
    чужой курс.
    """
    stranger = await outsider(course.creator_id)
    header = auth_header(stranger.id)

    edited = await client.put(
        f"/courses/{course.id}", headers=header, json={"name": "Чужое имя"}
    )
    deleted = await client.delete(f"/courses/{course.id}", headers=header)

    assert edited.status_code == 403, edited.text
    assert deleted.status_code == 403, deleted.text


async def test_a_stale_tag_stops_the_edit(client, auth_header, course):
    """Условная правка по If-Match.

    Метка приходит из предыдущего чтения. Если запись с тех пор
    изменилась, правка отклоняется — иначе два одновременных PUT молча
    перезаписывают друг друга, и переживает тот, кто пришёл вторым.
    """
    header = auth_header(course.creator_id)
    tag = (await client.get(f"/courses/{course.id}")).headers["etag"]

    first = await client.put(
        f"/courses/{course.id}",
        headers={**header, "If-Match": tag},
        json={"name": "Первая правка"},
    )
    assert first.status_code == 200, first.text

    second = await client.put(
        f"/courses/{course.id}",
        headers={**header, "If-Match": tag},
        json={"name": "Вторая правка"},
    )
    assert second.status_code == 412, second.text


async def test_a_matching_tag_lets_the_edit_through(
    client, auth_header, course
):
    header = auth_header(course.creator_id)
    tag = (await client.get(f"/courses/{course.id}")).headers["etag"]

    res = await client.put(
        f"/courses/{course.id}",
        headers={**header, "If-Match": tag},
        json={"name": "Новое имя"},
    )

    assert res.status_code == 200, res.text
    # Ответ несёт новую метку: следующая правка сверяется уже с ней.
    assert res.headers["etag"] != tag


async def test_replace_with_an_empty_body(client, auth_header, course):
    res = await client.put(
        f"/courses/{course.id}",
        headers=auth_header(course.creator_id),
        json={},
    )

    assert res.status_code == 200, res.text
    assert res.json()["name"] == course.name


async def test_a_null_in_a_required_field_is_rejected(
    client, auth_header, course
):
    """Отсутствие поля и null в нём — разные запросы.

    Поля правки необязательны, но пустоту в них записать нельзя:
    колонка объявлена NOT NULL. Пока схема разрешала null, он доезжал до
    базы, и клиент получал 500 на запросе, который схема разрешала.
    """
    res = await client.put(
        f"/courses/{course.id}",
        headers=auth_header(course.creator_id),
        json={"name": None},
    )

    assert res.status_code == 422, res.text
    assert [error["field"] for error in res.json()["errors"]] == ["name"]

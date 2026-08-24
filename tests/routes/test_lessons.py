from sqlalchemy import select

from app.db.models import Course, CourseLesson
from app.lib.data import build_lesson
from tests.conftest import MISSING_ID


async def test_index_counts_only_the_lessons_of_this_course(
    client, lesson, session
):
    """Счёт идёт по тому же условию, что и выборка.

    total — это число уроков этого курса, а не всех: иначе клиент
    рассчитывает страницы по чужим данным.
    """
    other = await session.scalar(
        select(Course).where(Course.id != lesson.course_id)
    )

    res = await client.get(f"/courses/{lesson.course_id}/lessons")
    empty = await client.get(f"/courses/{other.id}/lessons")

    assert res.status_code == 200, res.text
    assert res.json()["meta"]["total"] == 1
    assert empty.json()["meta"]["total"] == 0


async def test_show(client, lesson):
    res = await client.get(f"/courses/{lesson.course_id}/lessons/{lesson.id}")

    assert res.status_code == 200, res.text
    assert res.json() == {
        "id": lesson.id,
        "courseId": lesson.course_id,
        "name": lesson.name,
        "body": lesson.body,
    }


async def test_show_a_lesson_of_another_course(client, lesson, session):
    """Урок читается только в своём курсе.

    Адрес несёт оба идентификатора, и урок, запрошенный не у своего
    курса, не существует.
    """
    other = await session.scalar(
        select(Course).where(Course.id != lesson.course_id)
    )

    res = await client.get(f"/courses/{other.id}/lessons/{lesson.id}")

    assert res.status_code == 404, res.text


async def test_create(client, auth_header, course, refetch):
    data = build_lesson()

    res = await client.post(
        f"/courses/{course.id}/lessons",
        headers=auth_header(course.creator_id),
        json=data,
    )

    assert res.status_code == 201, res.text
    created = await refetch(CourseLesson, res.json()["id"])
    assert created.course_id == course.id
    assert created.name == data["name"]


async def test_create_in_a_missing_course(client, auth_header, user):
    res = await client.post(
        f"/courses/{MISSING_ID}/lessons",
        headers=auth_header(user.id),
        json=build_lesson(),
    )

    # Курса нет — 404, а не 500 на ограничении внешнего ключа уже в базе.
    assert res.status_code == 404, res.text


async def test_create_in_someone_elses_course(
    client, auth_header, course, outsider
):
    stranger = await outsider(course.creator_id)

    res = await client.post(
        f"/courses/{course.id}/lessons",
        headers=auth_header(stranger.id),
        json=build_lesson(),
    )

    assert res.status_code == 403, res.text


async def test_replace(client, auth_header, lesson, course, refetch):
    owner = (await refetch(Course, lesson.course_id)).creator_id

    res = await client.put(
        f"/courses/{lesson.course_id}/lessons/{lesson.id}",
        headers=auth_header(owner),
        json={"name": "Переименованный урок"},
    )

    assert res.status_code == 200, res.text
    updated = await refetch(CourseLesson, lesson.id)
    assert updated.name == "Переименованный урок"
    assert updated.body == lesson.body


async def test_destroy(client, auth_header, lesson, refetch):
    owner = (await refetch(Course, lesson.course_id)).creator_id

    res = await client.delete(
        f"/courses/{lesson.course_id}/lessons/{lesson.id}",
        headers=auth_header(owner),
    )

    assert res.status_code == 204, res.text
    assert await refetch(CourseLesson, lesson.id) is None


async def test_reading_is_open_and_writing_is_not(client, lesson):
    course_id = lesson.course_id
    requests = [
        client.post(f"/courses/{course_id}/lessons", json=build_lesson()),
        client.put(
            f"/courses/{course_id}/lessons/{lesson.id}", json={"name": "Имя"}
        ),
        client.delete(f"/courses/{course_id}/lessons/{lesson.id}"),
    ]

    for request in requests:
        res = await request
        assert res.status_code == 401, res.text

    listed = await client.get(f"/courses/{course_id}/lessons")
    assert listed.status_code == 200

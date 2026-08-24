from typing import Annotated

from fastapi import HTTPException, Query, Response, status
from sqlmodel import col, func, select

from app.db.models import CourseLesson
from app.dependencies import SessionDep
from app.lib.changes import changes
from app.lib.identifiers import ResourceId
from app.lib.pagination import Paging
from app.lib.serialization import to_schema
from app.policies import CoursePolicy
from app.routers.courses import find_course
from app.security import CurrentUserDep
from app.types.handlers.v1 import pydantic_gen as contract

CourseId = ResourceId
LessonId = ResourceId


async def _find_lesson(
    session: SessionDep, course_id: int, lesson_id: int
) -> CourseLesson:
    lesson = (
        await session.exec(
            select(CourseLesson).where(
                col(CourseLesson.course_id) == course_id,
                col(CourseLesson.id) == lesson_id,
            )
        )
    ).first()
    if lesson is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return lesson


async def _managed_course(
    session: SessionDep, course_id: int, user_id: int, action: str
):
    """Право на урок — это право на его курс.

    Урок добавляется в курс, поэтому проверяется владение курсом. Пока
    хватало любого токена, урок уезжал в чужой курс, а несуществующий
    курс упирался в ограничение внешнего ключа и давал 500.
    """
    course = await find_course(session, course_id)
    if not CoursePolicy.can_manage_lessons(course, user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"You can only {action} lessons of your own courses",
        )
    return course


async def index(
    session: SessionDep,
    course_id: CourseId,
    query: Annotated[contract.CoursesLessonsIndexQuery, Query()],
) -> contract.CourseLessonPage:
    paging = Paging.of(query)
    scope = col(CourseLesson.course_id) == course_id
    lessons = (
        await session.exec(
            select(CourseLesson)
            .where(scope)
            .order_by(col(CourseLesson.id))
            .limit(paging.limit)
            .offset(paging.offset)
        )
    ).all()
    # Счёт по тому же условию, что и выборка: total — это число уроков
    # этого курса, а не всех.
    total = await session.scalar(
        select(func.count()).select_from(CourseLesson).where(scope)
    )

    return contract.CourseLessonPage(
        data=[to_schema(contract.CourseLesson, lesson) for lesson in lessons],
        meta=paging.meta(total),
    )


async def show(
    session: SessionDep, course_id: CourseId, lesson_id: LessonId
) -> contract.CourseLesson:
    lesson = await _find_lesson(session, course_id, lesson_id)
    return to_schema(contract.CourseLesson, lesson)


async def create(
    session: SessionDep,
    user_id: CurrentUserDep,
    course_id: CourseId,
    data: contract.CourseLessonCreateDto,
) -> contract.CourseLesson:
    await _managed_course(session, course_id, user_id, "add")

    lesson = CourseLesson(name=data.name, body=data.body, course_id=course_id)
    session.add(lesson)
    await session.commit()

    return to_schema(contract.CourseLesson, lesson)


async def replace(
    session: SessionDep,
    user_id: CurrentUserDep,
    course_id: CourseId,
    lesson_id: LessonId,
    data: contract.CourseLessonEditDto,
) -> contract.CourseLesson:
    await _managed_course(session, course_id, user_id, "change")
    lesson = await _find_lesson(session, course_id, lesson_id)

    values = changes(data, schema="CourseLessonEditDTO")
    for field, value in values.items():
        setattr(lesson, field, value)
    if values:
        await session.commit()
        await session.refresh(lesson)

    return to_schema(contract.CourseLesson, lesson)


async def destroy(
    session: SessionDep,
    user_id: CurrentUserDep,
    course_id: CourseId,
    lesson_id: LessonId,
) -> Response:
    await _managed_course(session, course_id, user_id, "delete")
    lesson = await _find_lesson(session, course_id, lesson_id)

    await session.delete(lesson)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


handlers = {
    "coursesLessonsIndex": index,
    "coursesLessonsShow": show,
    "coursesLessonsCreate": create,
    "coursesLessonsUpdate": replace,
    "coursesLessonsDestroy": destroy,
}

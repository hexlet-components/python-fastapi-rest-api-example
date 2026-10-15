from typing import Annotated

from fastapi import Header, HTTPException, Query, Response, status
from sqlmodel import col, delete, select

from app.db.models import Course, CourseLesson
from app.dependencies import SessionDep
from app.lib.changes import changes
from app.lib.etag import ensure_matches, entity_tag
from app.lib.identifiers import ResourceId
from app.lib.pagination import fetch_page
from app.policies import CoursePolicy
from app.security import CurrentUserDep
from app.types.handlers.v1 import pydantic_gen as contract

CourseId = ResourceId
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description=(
            "Метка версии из предыдущего чтения. Необязательна; если "
            "прислана и запись с тех пор изменилась, правка отклоняется."
        ),
    ),
]


async def find_course(session: SessionDep, course_id: int) -> Course:
    course = await session.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    return course


async def owned_course(
    session: SessionDep, course_id: int, user_id: int, action: str
) -> Course:
    """Курс, которым распоряжается этот пользователь.

    Курс читается до правки, а не правится сразу: иначе проверить
    владельца не на чем, и любой предъявивший токен меняет чужой курс.
    """
    course = await find_course(session, course_id)
    if not CoursePolicy.can_update(course, user_id):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"You can only {action} your own courses"
        )
    return course


async def index(
    session: SessionDep,
    query: Annotated[contract.CoursesIndexQuery, Query()],
) -> contract.CoursePage:
    page = await fetch_page(
        session, select(Course).order_by(col(Course.id)), query
    )

    return contract.CoursePage(
        data=[
            contract.Course.model_validate(
                course, from_attributes=True, by_name=True
            )
            for course in page.items
        ],
        meta=contract.PageMeta.model_validate(page, from_attributes=True),
    )


async def show(
    session: SessionDep, course_id: CourseId, response: Response
) -> contract.Course:
    course = await find_course(session, course_id)
    # Метка версии ставится обработчиком, а не считается по телу ответа:
    # клиенту нужен валидатор, который он потом пришлёт в If-Match.
    response.headers["etag"] = entity_tag(course.updated_at)
    return contract.Course.model_validate(
        course, from_attributes=True, by_name=True
    )


async def create(
    session: SessionDep,
    user_id: CurrentUserDep,
    data: contract.CourseCreateDto,
) -> contract.Course:
    course = Course(
        name=data.name, description=data.description, creator_id=user_id
    )
    session.add(course)
    await session.commit()

    return contract.Course.model_validate(
        course, from_attributes=True, by_name=True
    )


async def replace(
    session: SessionDep,
    user_id: CurrentUserDep,
    course_id: CourseId,
    data: contract.CourseEditDto,
    response: Response,
    if_match: IfMatch = None,
) -> contract.Course:
    course = await owned_course(session, course_id, user_id, "change")
    ensure_matches(if_match, course.updated_at)

    values = changes(data, schema="CourseEditDTO")
    for field, value in values.items():
        setattr(course, field, value)
    if values:
        await session.commit()
        await session.refresh(course)

    response.headers["etag"] = entity_tag(course.updated_at)
    return contract.Course.model_validate(
        course, from_attributes=True, by_name=True
    )


async def destroy(
    session: SessionDep,
    user_id: CurrentUserDep,
    course_id: CourseId,
    if_match: IfMatch = None,
) -> Response:
    course = await owned_course(session, course_id, user_id, "delete")
    ensure_matches(if_match, course.updated_at)

    # Уроки удаляются явно и в одной транзакции с курсом, а не каскадом
    # из миграции: урок вне курса не существует, но поведение должно
    # быть видно в коде и покрыто тестом, а не спрятано в схеме.
    await session.exec(
        delete(CourseLesson).where(col(CourseLesson.course_id) == course_id)
    )
    await session.delete(course)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


handlers = {
    "coursesIndex": index,
    "coursesShow": show,
    "coursesCreate": create,
    "coursesUpdate": replace,
    "coursesDestroy": destroy,
}

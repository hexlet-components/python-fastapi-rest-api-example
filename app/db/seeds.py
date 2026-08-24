from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import Course, CourseLesson, User
from app.lib.data import build_course, build_lesson, build_user_record

# Адрес известен заранее: под ним получают токен контрактный прогон и
# ручные проверки примера.
SUPPORT_EMAIL = "support@hexlet.io"


async def seed(factory: async_sessionmaker) -> None:
    """Данные для разработки.

    Модуль тянет faker из группы dev, поэтому импортируется только там,
    где сиды нужны. Со статическим импортом боевая установка не
    поднималась бы вовсе — пакета в ней нет, — а если бы поднялась,
    завела бы в базе выдуманных пользователей.
    """
    async with factory() as session:
        users = [
            User(**await build_user_record()),
            User(**await build_user_record()),
            User(
                **await build_user_record(
                    email=SUPPORT_EMAIL,
                    full_name="Тото Поддерживающий",
                )
            ),
        ]
        session.add_all(users)
        await session.flush()

        author = users[1]
        courses = [
            Course(**build_course(creator_id=author.id)),
            Course(**build_course(creator_id=author.id)),
        ]
        session.add_all(courses)
        await session.flush()

        session.add(CourseLesson(**build_lesson(course_id=courses[1].id)))
        await session.commit()

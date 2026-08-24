from app.db.models import Course


class CoursePolicy:
    """Права на курс отдельно от обработчиков.

    Правило одно и то же для правки, удаления и работы с уроками, а
    список операций растёт: держать проверку в каждом обработчике значит
    однажды её там не написать.
    """

    @staticmethod
    def can_update(course: Course, user_id: int) -> bool:
        return course.creator_id == user_id

    @staticmethod
    def can_destroy(course: Course, user_id: int) -> bool:
        return course.creator_id == user_id

    # Уроки принадлежат курсу, поэтому право на них — это право на сам
    # курс.
    @staticmethod
    def can_manage_lessons(course: Course, user_id: int) -> bool:
        return course.creator_id == user_id

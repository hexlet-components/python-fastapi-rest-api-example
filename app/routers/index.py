from app.routers import courses, lessons, tokens, users
from app.types.handlers.v1.operations import Operations

# Все операции первой версии одним объявлением: его получает
# app/glue.py и вешает маршруты по контракту. Тип `Operations`
# напечатан из контракта (scripts/operations.py), поэтому `ty` ловит
# забытую или лишнюю операцию и ответ не той модели ещё до запуска.
handlers: Operations = {
    "coursesCreate": courses.create,
    "coursesDestroy": courses.destroy,
    "coursesIndex": courses.index,
    "coursesLessonsCreate": lessons.create,
    "coursesLessonsDestroy": lessons.destroy,
    "coursesLessonsIndex": lessons.index,
    "coursesLessonsShow": lessons.show,
    "coursesLessonsUpdate": lessons.replace,
    "coursesShow": courses.show,
    "coursesUpdate": courses.replace,
    "tokensCreate": tokens.create,
    "usersCreate": users.create,
    "usersDestroy": users.destroy,
    "usersIndex": users.index,
    "usersShow": users.show,
    "usersUpdate": users.replace,
}

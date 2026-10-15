from app.routers import courses, lessons, tokens
from app.routers.v2 import users
from app.types.handlers.v2.operations import Operations

# Курсы, уроки и токены между версиями не менялись, поэтому вторая
# версия берёт те же обработчики: для них тип ответа в `Operations` —
# модель первой версии. Расходятся только пользователи: во второй
# версии у них есть phone.
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

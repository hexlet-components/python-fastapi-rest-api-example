from app.routers import courses, lessons, tokens
from app.routers.v2 import users

# Курсы, уроки и токены между версиями не менялись, поэтому вторая
# версия берёт те же обработчики. Расходятся только пользователи: во
# второй версии у них есть phone.
handlers = {
    **users.handlers,
    **courses.handlers,
    **lessons.handlers,
    **tokens.handlers,
}

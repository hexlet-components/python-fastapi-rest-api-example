from app.routers import courses, lessons, tokens, users

# Все операции первой версии одним отображением: его получает
# app/glue.py и вешает маршруты по контракту. Забытая операция роняет
# приложение на старте, лишняя — тоже.
handlers = {
    **users.handlers,
    **courses.handlers,
    **lessons.handlers,
    **tokens.handlers,
}

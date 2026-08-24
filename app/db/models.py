from datetime import datetime, timezone

from sqlmodel import DateTime, Field, SQLModel, func


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampsMixin(SQLModel):
    """Время создания и правки в самих колонках.

    Тип колонки говорит, что в ней лежит время: `DateTime(timezone=True)`,
    а не число, чей смысл держится на кодеке ORM и комментарии рядом.

    Начальное значение даёт `server_default`, поэтому строка, вставленная
    мимо ORM (миграция, sql-скрипт), тоже получает время. Правку ведёт
    `onupdate`: серверный дефолт срабатывает только на INSERT, и без
    этого `updated_at` не менялся бы никогда.

    Время правки считает питон, а не база: `CURRENT_TIMESTAMP` в sqlite
    идёт с точностью до секунды, и две правки внутри одной секунды дали
    бы одинаковую метку версии — то есть условные запросы перестали бы
    замечать изменение.
    """

    # Аннотация без None, а значение по умолчанию None: колонка
    # объявлена NOT NULL, а заполняет её база своим дефолтом. Объявление
    # `datetime | None` сделало бы колонку nullable, и строка без времени
    # стала бы возможной.
    created_at: datetime = Field(
        default=None,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"server_default": func.now()},
    )
    updated_at: datetime = Field(
        default=None,
        nullable=False,
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={
            "server_default": func.now(),
            "onupdate": _now,
        },
    )


class User(TimestampsMixin, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    full_name: str | None = Field(default=None, max_length=100)
    email: str = Field(unique=True, index=True)
    password_digest: str
    # В контракте поле появляется только со второй версии. Nullable:
    # колонка добавляется существующей таблице, и NOT NULL упёрся бы в
    # уже лежащие строки.
    phone: str | None = None


class Course(TimestampsMixin, table=True):
    __tablename__ = "courses"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    description: str
    # Запрет, а не каскад: курс не перестаёт существовать от того, что
    # автор ушёл. Что делать с осиротевшими курсами — решение
    # приложения, и оно отвечает 409, а не молча сносит данные.
    creator_id: int = Field(foreign_key="users.id", ondelete="RESTRICT")


class CourseLesson(TimestampsMixin, table=True):
    __tablename__ = "course_lessons"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    body: str
    # Тоже запрет, хотя урок вне курса не существует: уроки удаляет
    # обработчик в одной транзакции с курсом. Поведение видно в коде и
    # покрыто тестом, а не спрятано в определении таблицы.
    course_id: int = Field(foreign_key="courses.id", ondelete="RESTRICT")

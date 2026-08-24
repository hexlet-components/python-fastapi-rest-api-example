from typing import Any

from pydantic import BaseModel

from app.contract import document
from app.lib.problems import ValidationProblemError
from app.types.handlers.v1.pydantic_gen import UnprocessableEntityErrorErrors


def _nullable_properties(schema_name: str, version: str) -> set[str]:
    schema = document(version)["components"]["schemas"][schema_name]
    return {
        name
        for name, prop in schema.get("properties", {}).items()
        if prop.get("nullable") or "null" in prop.get("type", [])
    }


def changes(
    data: BaseModel, *, schema: str, version: str = "v1"
) -> dict[str, Any]:
    """Поля правки, которые прислал клиент.

    `exclude_unset` различает «поле не присылали» и «прислали null»: без
    этого запрос с одним полем стирал бы все остальные.

    Отдельно отбивается null у поля, которое контракт объявил
    ненулевым. Сгенерированная модель этого не ловит: генератор печатает
    любое необязательное поле как `Optional[...]`, то есть теряет
    разницу между «можно не присылать» и «можно прислать пустым». Без
    проверки такой null доезжает до колонки NOT NULL, и клиент получает
    500 на запросе, который схема операции пропустила. Список
    обнуляемых полей берётся из самого контракта, а не переписывается
    сюда руками.
    """
    values = data.model_dump(exclude_unset=True)
    nullable = _nullable_properties(schema, version)
    fields = type(data).model_fields

    errors = [
        UnprocessableEntityErrorErrors(
            message="field must not be null",
            rule="not_nullable",
            field=fields[name].alias or name,
        )
        for name, value in values.items()
        if value is None and (fields[name].alias or name) not in nullable
    ]
    if errors:
        raise ValidationProblemError(errors)

    return values

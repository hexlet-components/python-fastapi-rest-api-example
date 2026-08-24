from typing import Any, TypeVar

from pydantic import BaseModel

Schema = TypeVar("Schema", bound=BaseModel)


def to_schema(schema: type[Schema], row: Any, **extra: Any) -> Schema:
    """Строка базы в модель контракта.

    Поля берутся по именам, объявленным в модели, и подставляются под
    псевдонимами контракта. Готовый `model_validate(row,
    from_attributes=True)` для этого не годится: он ищет у объекта
    атрибут с именем псевдонима, то есть `fullName`, — такого атрибута у
    строки нет, и поле молча уезжает пустым. Проверка при этом
    проходит: поле необязательное.
    """
    values: dict[str, Any] = {}
    for name, field in schema.model_fields.items():
        if name in extra:
            continue
        if hasattr(row, name):
            values[field.alias or name] = getattr(row, name)

    return schema.model_validate({**values, **extra})

"""Линт контракта.

Проверяется то, что видит клиент: документ разбирается настоящим
валидатором OpenAPI, а не читается глазами. Плюс два правила своих —
описание и идентификатор у каждой операции: по первому клиент понимает,
что операция делает, по второму сгенерированный клиент называет метод.

Правила про авторизацию здесь нет намеренно: открытые операции — это
решение, а не упущение. Список курсов, регистрация и выдача токена
доступны без токена по определению.
"""

import json
import pathlib
import sys

from openapi_spec_validator import validate

DOCUMENTS = sorted(
    (pathlib.Path(__file__).resolve().parents[1] / "openapi").glob("*.json")
)


def check_operations(document: dict) -> list[str]:
    problems = []
    for path, operations in document["paths"].items():
        for method, operation in operations.items():
            where = f"{method.upper()} {path}"
            if not operation.get("summary"):
                problems.append(f"{where}: нет описания (summary)")
            if not operation.get("operationId"):
                problems.append(f"{where}: нет operationId")
    return problems


def main() -> int:
    if not DOCUMENTS:
        print("контракта нет — сначала make generate-openapi", file=sys.stderr)
        return 1

    problems = []
    for path in DOCUMENTS:
        document = json.loads(path.read_text())
        validate(document)
        problems += [
            f"{path.name}: {item}" for item in check_operations(document)
        ]
        print(f"{path.name}: документ валиден")

    for problem in problems:
        print(problem, file=sys.stderr)

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""Таблица маршрутов приложения.

Операции берутся из контракта — того же документа, который приложение
отдаёт клиенту, — поэтому в таблице видно и объявленную авторизацию.
Отдельный список маршрутов в исходниках не ведётся: их регистрируют
роутеры.
"""

import os

os.environ.setdefault("JWT_SECRET", "routes-listing-only-secret-0123456789")

from fastapi.routing import iter_route_contexts  # noqa: E402

from app.contract import VERSIONS, document  # noqa: E402
from app.main import create_app  # noqa: E402


def main() -> None:
    app = create_app()

    for version, prefix in VERSIONS.items():
        print(f"== {version} ==")
        for path, operations in sorted(document(version)["paths"].items()):
            for method, operation in sorted(operations.items()):
                auth = "auth" if operation.get("security") else ""
                print(
                    f"{method.upper():7} {prefix}{path:45} "
                    f"{operation['operationId']:22} {auth}"
                )

    # Вне контракта: операционные адреса и документация. Их нет в
    # спеке — это не часть API.
    print("== вне контракта ==")
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if getattr(route, "include_in_schema", True) or context.path is None:
            continue
        for method in sorted(getattr(route, "methods", []) or []):
            print(f"{method:7} {context.path}")


if __name__ == "__main__":
    main()

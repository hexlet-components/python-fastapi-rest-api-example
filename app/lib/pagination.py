from dataclasses import dataclass
from math import ceil
from typing import Protocol


class PageQuery(Protocol):
    """Постраничный вход любой операции контракта.

    Границы и значения по умолчанию объявлены в контракте, поэтому у
    каждой операции своя сгенерированная модель запроса — а считают
    страницу они одинаково.
    """

    page: int | None
    per_page: int | None


@dataclass(frozen=True)
class Paging:
    page: int
    per_page: int

    @classmethod
    def of(cls, query: PageQuery) -> "Paging":
        return cls(page=query.page or 1, per_page=query.per_page or 10)

    @property
    def limit(self) -> int:
        return self.per_page

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page

    def meta(self, total: int) -> dict[str, int]:
        """Метаданные страницы под псевдонимами контракта.

        Возвращается отображение, а не готовая модель: у каждой версии
        контракта свой сгенерированный PageMeta, и общая на все версии
        модель не подошла бы ни одной.
        """
        return {
            "page": self.page,
            "perPage": self.per_page,
            "total": total,
            "totalPages": ceil(total / self.per_page),
        }

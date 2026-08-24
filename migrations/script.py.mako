"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

# Порядок импортов и переносы строк здесь уже такие, какие требует
# линтер: иначе каждая сгенерированная миграция сразу же роняла бы
# make lint. Остаток форматирования доводит ruff в make
# migration-generate.
#
# sqlmodel импортируется всегда: автогенерация печатает его тип строки
# (`sqlmodel.sql.sqltypes.AutoString`), и без импорта миграция падает на
# NameError уже при накатывании.
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op
${imports if imports else ""}

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Upgrade schema."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Downgrade schema."""
    ${downgrades if downgrades else "pass"}

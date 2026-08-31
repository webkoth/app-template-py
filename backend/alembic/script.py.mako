## Шапка отличается от стоковой alembic намеренно: та пишет
## `from typing import Sequence, Union` и `Union[...]`, а на них ruff в
## `make check` даёт UP035, UP007 и I001 — то есть каждая сгенерированная
## миграция рождалась бы красной. Здесь сразу PEP 604 и collections.abc,
## а порядок импортов — тот, которого требует isort этого проекта.
## Строки, начинающиеся с ##, — комментарии Mako: в сам файл миграции они
## не попадают.
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""

from collections.abc import Sequence

import sqlalchemy as sa
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

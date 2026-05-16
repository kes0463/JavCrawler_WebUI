"""stamp v8 schema — Alembic 시작점 (DDL 없음, user_version 8→9)

Revision ID: 0001_stamp_v8
Revises:
Create Date: 2026-05-16

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_stamp_v8"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# v8 이하: database.py init_db / _migrate_v*
# v9+: Alembic (본 revision부터)
_TARGET_USER_VERSION = 9


def upgrade() -> None:
    conn = op.get_bind()
    current = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
    if int(current) < _TARGET_USER_VERSION:
        conn.exec_driver_sql(f"PRAGMA user_version = {_TARGET_USER_VERSION}")


def downgrade() -> None:
    conn = op.get_bind()
    conn.exec_driver_sql("PRAGMA user_version = 8")

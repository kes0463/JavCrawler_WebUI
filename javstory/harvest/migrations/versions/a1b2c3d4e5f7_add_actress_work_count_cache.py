"""add actresses.work_count and works_updated_at cache columns

Revision ID: a1b2c3d4e5f7
Revises: f2a3b4c5d6e7
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    existing = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(actresses)")]

    if "work_count" not in existing:
        op.add_column(
            "actresses",
            sa.Column("work_count", sa.Integer(), nullable=False, server_default="0"),
        )
        print("[Migration a1b2c3d4e5f7] actresses.work_count 추가")

    if "works_updated_at" not in existing:
        op.add_column(
            "actresses",
            sa.Column("works_updated_at", sa.DateTime(), nullable=True),
        )
        print("[Migration a1b2c3d4e5f7] actresses.works_updated_at 추가")

    op.create_index("ix_actresses_work_count", "actresses", ["work_count"], unique=False)

    current = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
    if int(current) < 15:
        conn.exec_driver_sql("PRAGMA user_version = 15")
    print("[Migration a1b2c3d4e5f7] actress work_count cache columns ready")


def downgrade() -> None:
    op.drop_index("ix_actresses_work_count", table_name="actresses")
    pass

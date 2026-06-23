"""add actress_works link table (actress ↔ product_code)

Revision ID: f2a3b4c5d6e7
Revises: e1a2b3c4d5e6
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actress_works",
        sa.Column("actress_id", sa.Integer(), nullable=False),
        sa.Column("product_code", sa.String(length=50), nullable=False),
        sa.Column("match_source", sa.String(length=32), nullable=True),
        sa.Column("matched_token", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["actress_id"], ["actresses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_code"], ["jav_metadata.product_code"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("actress_id", "product_code"),
    )
    op.create_index("ix_actress_works_actress_id", "actress_works", ["actress_id"], unique=False)
    op.create_index("ix_actress_works_product_code", "actress_works", ["product_code"], unique=False)

    conn = op.get_bind()
    current = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
    if int(current) < 14:
        conn.exec_driver_sql("PRAGMA user_version = 14")
    print("[Migration f2a3b4c5d6e7] actress_works table created")


def downgrade() -> None:
    op.drop_index("ix_actress_works_product_code", table_name="actress_works")
    op.drop_index("ix_actress_works_actress_id", table_name="actress_works")
    op.drop_table("actress_works")

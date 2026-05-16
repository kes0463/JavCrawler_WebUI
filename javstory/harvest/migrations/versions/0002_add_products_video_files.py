"""add products and video_files (DB v2 P2)

Revision ID: 0002_add_products_video_files
Revises: 0001_stamp_v8
Create Date: 2026-05-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_products_video_files"
down_revision: Union[str, Sequence[str], None] = "0001_stamp_v8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TARGET_USER_VERSION = 10


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("jav_metadata_id", sa.Integer(), nullable=True),
        sa.Column("folder_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["jav_metadata_id"], ["jav_metadata.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jav_metadata_id"),
        sa.UniqueConstraint("sku"),
    )
    op.create_index("idx_products_folder_path", "products", ["folder_path"], unique=False)
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=True)

    op.create_table(
        "video_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("part_order", sa.Integer(), nullable=False),
        sa.Column("video_relpath", sa.Text(), nullable=False),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("fingerprint", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "part_order", name="uq_video_files_product_order"),
        sa.UniqueConstraint("product_id", "video_relpath", name="uq_video_files_product_relpath"),
    )
    op.create_index(op.f("ix_video_files_product_id"), "video_files", ["product_id"], unique=False)

    conn = op.get_bind()
    current = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
    if int(current) < _TARGET_USER_VERSION:
        conn.exec_driver_sql(f"PRAGMA user_version = {_TARGET_USER_VERSION}")


def downgrade() -> None:
    op.drop_index(op.f("ix_video_files_product_id"), table_name="video_files")
    op.drop_table("video_files")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_index("idx_products_folder_path", table_name="products")
    op.drop_table("products")
    conn = op.get_bind()
    conn.exec_driver_sql("PRAGMA user_version = 9")

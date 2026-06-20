"""add actress created_at/updated_at timestamps and fix profile_image_url to Text

Revision ID: e1a2b3c4d5e6
Revises: d5a638a6528e
Create Date: 2026-06-20

Additive only:
- actresses.created_at  (DATETIME, nullable)
- actresses.updated_at  (DATETIME, nullable)
- actresses.profile_image_url 컬럼은 SQLite에서 TEXT/VARCHAR 타입 변경이
  사실상 no-op(선언적 타입만 다름)이므로 별도 처리 없이 모델 정의만 Text로 변경.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'd5a638a6528e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    existing = [row[1] for row in conn.exec_driver_sql("PRAGMA table_info(actresses)")]

    # SQLite는 ALTER TABLE ADD COLUMN에서 함수형 DEFAULT(CURRENT_TIMESTAMP 등)를 허용하지 않음.
    # nullable로만 추가하고 SQLAlchemy ORM이 INSERT 시 채운다.
    if 'created_at' not in existing:
        op.add_column('actresses', sa.Column('created_at', sa.DateTime(), nullable=True))
        print('[Migration e1a2b3c4d5e6] actresses.created_at 추가')

    if 'updated_at' not in existing:
        op.add_column('actresses', sa.Column('updated_at', sa.DateTime(), nullable=True))
        print('[Migration e1a2b3c4d5e6] actresses.updated_at 추가')

    current = conn.exec_driver_sql("PRAGMA user_version").scalar() or 0
    if int(current) < 13:
        conn.exec_driver_sql("PRAGMA user_version = 13")

    print('[Migration e1a2b3c4d5e6] Actress 타임스탬프 마이그레이션 완료')


def downgrade() -> None:
    # SQLite는 DROP COLUMN을 지원하지 않으므로 downgrade는 no-op
    pass

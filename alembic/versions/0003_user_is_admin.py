"""users.is_admin カラム追加

Revision ID: 0003_user_is_admin
Revises: 0002_likes_unique
Create Date: 2026-05-01

username 文字列での admin 判定をやめ、専用フラグで認可するための列追加。
既存ユーザーは全員 is_admin=False とする。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_user_is_admin"
down_revision: Union[str, None] = "0002_likes_unique"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_admin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_admin")

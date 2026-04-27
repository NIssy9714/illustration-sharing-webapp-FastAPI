"""likes に UNIQUE(user_id, post_id) を追加

Revision ID: 0002_likes_unique
Revises: 0001_init
Create Date: 2026-04-27

二重いいね登録を DB レベルで防ぐ。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_likes_unique"
down_revision: Union[str, None] = "0001_init"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 既存の重複行を削除（同一 user_id+post_id の組のうち最小 id 以外を消す）
    op.execute(
        """
        DELETE FROM likes
        WHERE id NOT IN (
            SELECT min_id FROM (
                SELECT MIN(id) AS min_id
                FROM likes
                GROUP BY user_id, post_id
            ) AS dedup
        )
        """
    )
    with op.batch_alter_table("likes") as batch_op:
        batch_op.create_unique_constraint(
            "uq_likes_user_post",
            ["user_id", "post_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("likes") as batch_op:
        batch_op.drop_constraint("uq_likes_user_post", type_="unique")

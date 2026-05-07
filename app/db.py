"""FastAPI 用のデータベース管理モジュール。

SQLAlchemy で SQLite/PostgreSQL を扱う。
スキーマ変更は Alembic 経由で行うこと（init_db は dev 用の補助）。
"""

import os
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# SQLite 以外（Postgres 等）では check_same_thread を渡さない
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ==============================================================================
# モデル定義
# ==============================================================================


class User(Base):
    """ユーザーテーブル."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    # 管理者フラグ。username 文字列ではなくこのフラグで認可判定する
    is_admin = Column(Boolean, nullable=False, default=False, server_default="0")


class Post(Base):
    """投稿テーブル."""

    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=True)
    body = Column(Text, nullable=True)
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Like(Base):
    """いいねテーブル。

    1 ユーザー × 1 投稿に対して 1 件しか作れない（UNIQUE 制約）。
    """

    __tablename__ = "likes"
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_likes_user_post"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)


# ==============================================================================
# ユーティリティ関数
# ==============================================================================


def get_db():
    """リクエストごとのセッションを取得."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# スキーマ初期化は Alembic マイグレーション (`alembic upgrade head`) で行う。
# 起動時には `app.core.migrate.run_migrations` 経由で自動実行される。


# アップロード先ディレクトリ設定
UPLOADS_DIR = os.path.join("static", "uploads")


def setup_uploads_dir():
    """アップロード先ディレクトリを作成（存在しない場合）."""
    os.makedirs(UPLOADS_DIR, exist_ok=True)

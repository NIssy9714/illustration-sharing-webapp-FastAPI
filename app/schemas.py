"""Pydantic スキーマ定義。

API のリクエスト/レスポンスのバリデーションに使用します。
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ==============================================================================
# ユーザー関連スキーマ
# ==============================================================================


RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "system",
}  # 予約ユーザー名（大文字小文字無視）


class UserRegister(BaseModel):
    """ユーザー登録リクエストスキーマ."""

    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("username")  # username フィールドのバリデーションを定義
    @classmethod  # クラスメソッドとして定義（インスタンス化せずに呼び出せるようにするため）
    def validate_username(cls, username):  # username を引数に取るバリデーション関数
        """予約ユーザー名（admin など）の登録を大文字小文字無視で拒否."""
        # 認可判定を username に依存しているため、なりすまし登録を防ぐ
        if username.strip().lower() in RESERVED_USERNAMES:
            raise ValueError("このユーザー名は使用できません")
        return username

    @field_validator("password")
    @classmethod
    def validate_password(cls, password):
        """パスワードが半角英数字・記号を1つ以上含むことを検証."""
        if not re.match(r"^[\x21-\x7E]+$", password):
            raise ValueError(
                "パスワードは8文字以上・半角英数字・記号を1つ以上含むようにしてください",
            )
        if not re.search(r"[a-zA-Z0-9]", password):
            raise ValueError(
                "パスワードは8文字以上・半角英数字・記号を1つ以上含むようにしてください",
            )
        if not re.search(r"[\x21-\x2F\x3A-\x40\x5B-\x60\x7B-\x7E]", password):
            raise ValueError(
                "パスワードは8文字以上・半角英数字・記号を1つ以上含むようにしてください",
            )
        return password


class UserLogin(BaseModel):
    """ログインリクエストスキーマ."""

    username: str
    password: str


class UserResponse(BaseModel):
    """ユーザー情報レスポンススキーマ."""

    id: int
    username: str

    class Config:
        from_attributes = True


# ==============================================================================
# 投稿関連スキーマ
# ==============================================================================


class PostCreate(BaseModel):
    """投稿作成リクエストスキーマ."""

    title: str = Field(..., min_length=1, max_length=255)
    body: str | None = Field(default="", max_length=140)


class PostResponse(BaseModel):
    """投稿レスポンススキーマ."""

    id: int
    user_id: int
    title: str
    filename: str | None = None
    body: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class PostWithLikes(PostResponse):
    """いいね数を含む投稿レスポンススキーマ."""

    like_count: int = 0


# ==============================================================================
# いいね関連スキーマ
# ==============================================================================


class LikeResponse(BaseModel):
    """いいね操作レスポンススキーマ."""

    liked: bool
    like_count: int


# ==============================================================================
# 検索関連スキーマ
# ==============================================================================


class SearchResults(BaseModel):
    """検索結果レスポンススキーマ."""

    search_keyword: str
    posts: list[PostResponse]


# ==============================================================================
# エラーレスポンススキーマ
# ==============================================================================


class ErrorResponse(BaseModel):
    """エラーレスポンススキーマ."""

    detail: str

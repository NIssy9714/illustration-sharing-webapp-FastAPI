"""アプリケーション全体で参照する設定モジュール。

Pydantic Settings で .env / 環境変数から読み込む。
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数で上書き可能な設定値."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 動作環境
    app_env: str = Field(default="dev", description="dev/staging/prod")
    app_name: str = Field(default="portfolio-api")

    # 認証
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="JWT 署名鍵。本番では必ず差し替える",
    )
    access_token_expire_minutes: int = 30
    cookie_secure: bool = Field(
        default=False,
        description="本番では True。HTTPS でしか Cookie を送信しない",
    )
    cookie_samesite: str = Field(default="lax", description="strict/lax/none")

    # DB
    database_url: str = Field(default="sqlite:///./database.db")

    # CORS
    allowed_origins: str = Field(
        default="http://localhost:8000",
        description="カンマ区切りで許可オリジンを列挙",
    )

    # 監視
    sentry_dsn: str | None = None

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    """設定をプロセス内でシングルトン化して返す."""
    return Settings()

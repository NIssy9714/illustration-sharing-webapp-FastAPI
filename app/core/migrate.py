"""Alembic マイグレーションをアプリ起動時に実行するためのユーティリティ。

本番では `Base.metadata.create_all` を使わず、
このモジュール経由で `alembic upgrade head` を呼ぶ。
"""

import os

from alembic import command
from alembic.config import Config
from app.core.config import get_settings
from app.core.logging import get_logger


def run_migrations(alembic_ini_path: str) -> None:
    """alembic upgrade head を実行する."""
    log = get_logger("app.migrate")
    settings = get_settings()

    alembic_config = Config(alembic_ini_path)
    # script_location を絶対パスで上書きし、cwd 依存をなくす
    alembic_config.set_main_option(
        "script_location",
        os.path.join(os.path.dirname(alembic_ini_path), "alembic"),
    )
    alembic_config.set_main_option("sqlalchemy.url", settings.database_url)

    log.info("migrations.start", database_url=settings.database_url)
    command.upgrade(cfg=alembic_config, revision="head")
    log.info("migrations.done")

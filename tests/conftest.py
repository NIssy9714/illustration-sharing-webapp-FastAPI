import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# プロジェクトルートを import パスに追加
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# settings 読込前に環境変数を確定
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ALLOWED_ORIGINS", "http://testserver")


@pytest.fixture(scope="session")
def client():
    from app.core.limiter import limiter
    from app.db import Base, get_db
    from app.main import app

    # テスト中はレート制限を無効化（同一クライアントから連発するため）
    limiter.enabled = False

    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=test_engine,
    )
    Base.metadata.create_all(bind=test_engine)

    def override_get_db():
        test_db_session = TestSessionLocal()
        try:
            yield test_db_session
        finally:
            test_db_session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)

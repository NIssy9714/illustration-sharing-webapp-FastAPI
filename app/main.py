"""FastAPI アプリケーションのメインエントリーポイント。

責務:
- FastAPI アプリの生成と設定
- ミドルウェア（CORS, レート制限）の登録
- ルーターの登録
- ライフサイクル（DB 初期化、ログ/Sentry 設定）
- テンプレート用 GET ルート
"""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import configure_logging, configure_sentry, get_logger
from app.core.migrate import run_migrations
from app.db import Like, Post, get_db, setup_uploads_dir
from app.routers import auth, posts, search
from app.routers.auth import get_optional_user

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALEMBIC_INI = os.path.join(BASE_DIR, "alembic.ini")
settings = get_settings()

# ==============================================================================
# テンプレート設定
# ==============================================================================
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ==============================================================================
# ライフサイクル管理
# ==============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクルを管理."""
    configure_logging()
    configure_sentry()
    log = get_logger("app.lifespan")

    if settings.is_prod and settings.secret_key == "dev-secret-key-change-in-production":
        raise RuntimeError("SECRET_KEY が本番のデフォルトのままです。設定し直してください")

    # スキーマは Alembic を起動時に実行（test 環境は conftest が独自に作るのでスキップ）
    if settings.app_env != "test":
        run_migrations(ALEMBIC_INI)
    setup_uploads_dir()
    log.info("startup", database_url=settings.database_url, app_env=settings.app_env)
    yield
    log.info("shutdown")


# ==============================================================================
# アプリケーション初期化
# ==============================================================================


app = FastAPI(
    title="Portfolio API",
    description="ポートフォリオ Web アプリケーション API",
    version="1.0.0",
    lifespan=lifespan,
)

# レート制限（slowapi）
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS（環境変数 ALLOWED_ORIGINS をカンマ区切りで読む）
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# static ファイルをマウント
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "static")),
    name="static",
)


# ==============================================================================
# ルーター登録
# ==============================================================================


app.include_router(auth.router)
app.include_router(posts.router)
app.include_router(search.router)


# ==============================================================================
# テンプレート用 GET ルート
# ==============================================================================


def _user_ctx(user) -> dict:
    if user is None:
        return {"current_user": None}
    return {"current_user": {"id": user.id, "username": user.username}}


@app.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    posts_list = db.query(Post).order_by(desc(Post.created_at)).all()
    like_counts = {
        p.id: db.query(Like).filter(Like.post_id == p.id).count() for p in posts_list
    }
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "posts": posts_list,
            "like_counts": like_counts,
            **_user_ctx(current_user),
        },
    )


@app.get("/login")
def login_page(request: Request, current_user=Depends(get_optional_user)):
    return templates.TemplateResponse(
        "login.html",
        {"request": request, **_user_ctx(current_user)},
    )


@app.get("/register")
def register_page(request: Request, current_user=Depends(get_optional_user)):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, **_user_ctx(current_user)},
    )


@app.get("/upload")
def upload_page(request: Request, current_user=Depends(get_optional_user)):
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, **_user_ctx(current_user)},
    )


@app.get("/search")
def search_page(
    request: Request,
    search_query: str = "",
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    keyword = search_query.strip()[:100]
    posts_list = (
        db.query(Post)
        .filter(Post.title.ilike(f"%{keyword}%"))
        .order_by(desc(Post.created_at))
        .all()
    )
    return templates.TemplateResponse(
        "search_results.html",
        {
            "request": request,
            "posts": posts_list,
            "search_keyword": keyword,
            **_user_ctx(current_user),
        },
    )


@app.get("/post/{id}")
def post_page(
    request: Request,
    id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    post = db.query(Post).filter(Post.id == id).first()
    if not post:
        raise HTTPException(status_code=404, detail="投稿が見つかりません")
    like_count = db.query(Like).filter(Like.post_id == id).count()
    return templates.TemplateResponse(
        "post.html",
        {
            "request": request,
            "post": post,
            "like_count": like_count,
            **_user_ctx(current_user),
        },
    )


@app.get("/health")
def health_check():
    """ヘルスチェックエンドポイント."""
    return {"status": "ok"}


# ==============================================================================
# エラーハンドリング
# ==============================================================================


@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request, exc):
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request, exc):
    return await request_validation_exception_handler(request, exc)


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    log = get_logger("app.unhandled")
    log.exception("unhandled_exception", path=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

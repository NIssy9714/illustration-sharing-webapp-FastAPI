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
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.limiter import limiter
from app.core.logging import configure_logging, configure_sentry, get_logger
from app.core.migrate import run_migrations
from app.db import Like, Post, get_db, setup_uploads_dir
from app.routers import auth, posts, search
from app.routers.auth import get_optional_user

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)  # このファイル（main.py）の親ディレクトリの親ディレクトリを BASE_DIR として定義。これでプロジェクトのルートディレクトリを指すことになる
ALEMBIC_INI = os.path.join(
    BASE_DIR, "alembic.ini"
)  # Alembic（DB マイグレーションツール）の設定ファイルのパスを定義。これを使ってマイグレーションを実行する
settings = get_settings()  # 環境変数から設定を読み込む。これで settings.database_url や settings.is_prod などが使えるようになる

# ==============================================================================
# テンプレート設定
# ==============================================================================
templates = Jinja2Templates(
    directory=os.path.join(BASE_DIR, "templates")
)  # Jinja2Templates を使ってテンプレートエンジンを設定。テンプレートファイルはプロジェクトの templates ディレクトリに置くことになる


# ==============================================================================
# ライフサイクル管理
# ==============================================================================


@asynccontextmanager  # FastAPI の lifespan（ライフサイクル）イベントを定義。アプリの起動と終了のタイミングで特定の処理を実行できるようになる
async def lifespan(
    app: FastAPI,
):  # アプリのライフサイクルイベントの関数。ここでアプリの起動時と終了時の処理を定義する
    """アプリケーションのライフサイクルを管理."""
    configure_logging()  # ログ出力の設定を初期化。これ以降log.info(...)などが正しい形式で記録される
    configure_sentry()  # Sentry(エラー監視サービス)の初期化。例外が起きたら自動で外部に通知
    log = get_logger(
        "app.lifespan"
    )  # app.lifespanという名前のロガーを取得。名前を分けると後でフィルタして見られる

    if (
        settings.is_prod and settings.secret_key == "dev-secret-key-change-in-production"
    ):  # 本番環境で SECRET_KEY がデフォルトのままになっていないかチェック。SECRET_KEY はセッション管理や CSRF トークンの生成に使われる重要な値なので、デフォルトのままだとセキュリティリスクになる
        raise RuntimeError(
            "SECRET_KEY が本番のデフォルトのままです。設定し直してください"
        )  # もし本番環境で SECRET_KEY がデフォルトのままだったらエラーを出して起動を止める。これでうっかり本番でセキュリティ設定を忘れるのを防ぐ

    # 本番では CSRF 緩和につながる Cookie 設定を拒否
    if settings.is_prod:  # 本番環境では、セキュリティの観点から Cookie の設定を厳しくする必要がある。例えば、HTTPS 以外で送られるのを防ぐために Secure 属性を付けたり、CSRF 攻撃を防ぐために SameSite 属性を Strict にするなど。これらの設定がされていない場合は起動時にエラーを出して知らせる
        if not settings.cookie_secure:  # 本番環境で Cookie Secure 属性が true になっていない場合はエラーを出す。Secure 属性がないと、HTTP でも Cookie が送られてしまい、通信が盗聴されたときにセッションが乗っ取られるリスクがある
            raise RuntimeError(
                "本番では COOKIE_SECURE=true を設定してください（HTTPS 限定送信）"
            )  # raiseは例外処理。本番環境で Cookie SameSite 属性が Strict になっていない場合はエラーを出す。SameSite 属性が Strict でないと、CSRF 攻撃のリスクが高まる。Strict にすることで、外部サイトからのリクエストには Cookie が送られなくなり、CSRF 攻撃を防止できる
        if (
            settings.cookie_samesite.lower() != "strict"
        ):  # samesiteはCSRF対策を行うためのCookie属性。本番環境で Cookie SameSite 属性が Strict になっていない場合はエラーを出す。設定しないとCSRF 攻撃のリスクが高まる。Strictは一番厳しい設定値であり、外部サイトからのリクエストには Cookie が送られなくなり、CSRF 攻撃を防止できるがサービス間連携などの利便性は低下する。
            raise RuntimeError(
                "本番では COOKIE_SAMESITE=strict を設定してください（CSRF 防御）"
            )  # raiseは例外処理。本番環境で Cookie SameSite 属性が Strict になっていない場合はエラーを出す。設定しないとCSRF 攻撃のリスクが高まる。Strict にすることで、外部サイトからのリクエストには Cookie が送られなくなり、CSRF 攻撃を防止できる

    # スキーマは Alembic を起動時に実行（test 環境は conftest が独自に作るのでスキップ）
    if (
        settings.app_env != "test"
    ):  # テスト環境では、テストごとに独自のデータベースを作成してマイグレーションを実行するため、ここではマイグレーションをスキップする。これでテストのセットアップが速くなり、テストごとにクリーンな状態でDBを使用できるようになる
        run_migrations(
            ALEMBIC_INI
        )  # Alembic を使ってデータベースのマイグレーションを実行。これで DB スキーマが最新の状態に保たれる
    setup_uploads_dir()  # アップロードされたファイルを保存するディレクトリを作成。これでファイルの保存先が確保
    # 接続文字列に含まれるパスワードはログに出さない
    try:
        masked_database_url = make_url(
            settings.database_url
        ).render_as_string(  # SQLAlchemy の URL オブジェクトを作成して、パスワードをマスクした状態で文字列に変換。これでログにデータベースの接続情報を出すときに、パスワードが表示されないようになる
            hide_password=True,  # パスワードをマスクするオプション。これを True にすると、URL のパスワード部分が <hidden> として表示されるようになる
        )
    except Exception:  # もし settings.database_url が不正な形式で URL として解析できない場合は、例外が発生する可能性がある。その場合は、マスクされた URL として "<unparseable>" を使う。これでログに不正な URL が出るのを防ぐ
        masked_database_url = "<unparseable>"  # URL の解析に失敗した場合のマスクされた URL の値。これをログに出すことで、URL の形式が正しくないことがわかるようになる
    log.info(
        "startup", database_url=masked_database_url, app_env=settings.app_env
    )  # アプリの起動時にログを出す。これでアプリが起動したことと、どのデータベースに接続しているか、どの環境で動いているかがわかるようになる
    yield  # ここでアプリが起動している状態になる。yield の前が起動時の処理、yield の後がシャットダウン時の処理になる
    log.info("shutdown")


# ==============================================================================
# アプリケーション初期化
# ==============================================================================


app = FastAPI(  # FastAPI 本体のインスタンス生成。これ以降 app.get(...) などでルートを登録できる
    title="Portfolio API",  # OpenAPI ドキュメント (/docs) に表示されるタイトル
    description="ポートフォリオ Web アプリケーション API",  # /docs に表示される説明文
    version="1.0.0",  # API のバージョン。クライアント側で挙動の互換性確認に使われる
    lifespan=lifespan,  # 上で定義した lifespan を登録。起動・終了時の処理がここで紐付く
)

# レート制限（slowapi）
app.state.limiter = limiter  # slowapi のレート制限器を app の状態に保存。各ルーターから @limiter.limit(...) で参照される
app.add_exception_handler(
    RateLimitExceeded, _rate_limit_exceeded_handler
)  # 制限超過時 (RateLimitExceeded) に 429 を返す既定ハンドラを登録。これが無いと 500 エラーになる
app.add_middleware(
    SlowAPIMiddleware
)  # 全リクエストを slowapi が監視できるようミドルウェアとして挿入。これでレート制限が機能する

# CORS（環境変数 ALLOWED_ORIGINS をカンマ区切りで読む）
app.add_middleware(
    CORSMiddleware,  # ブラウザの同一オリジンポリシーを越えて他ドメインからのアクセスを許可する仕組み
    allow_origins=settings.allowed_origins_list,  # 許可するオリジンの一覧。"*" にすると全許可だが credentials と併用不可なので明示列挙が安全
    allow_credentials=True,  # Cookie や Authorization ヘッダの送信を許可。ログイン状態を跨ぐなら必須
    allow_methods=[
        "GET",
        "POST",
        "DELETE",
        "OPTIONS",
    ],  # 許可する HTTP メソッド。PUT/PATCH を使わないなら入れない方が攻撃面が減る
    allow_headers=[
        "Authorization",
        "Content-Type",
    ],  # 許可するリクエストヘッダ。JWT 用の Authorization と JSON 用 Content-Type を最小限で許可
)

# static ファイルをマウント
app.mount(
    "/static",  # URL のプレフィックス。/static/xxx.png のようにアクセスされる
    StaticFiles(
        directory=os.path.join(BASE_DIR, "static")
    ),  # 実ファイルが置かれるディレクトリ。ここを直接配信する
    name="static",  # url_for("static", path=...) でテンプレート側から逆引きできる名前
)


# ==============================================================================
# ルーター登録
# ==============================================================================


app.include_router(auth.router)  # /auth/register, /auth/login など認証系のエンドポイント群を登録
app.include_router(posts.router)  # /posts 配下の投稿 CRUD・いいね操作のエンドポイント群を登録
app.include_router(
    search.router
)  # /search の検索 API（JSON 応答）を登録。テンプレート版の /search とは別物


# ==============================================================================
# テンプレート用 GET ルート
# ==============================================================================


def _build_user_context(
    user,
) -> dict:  # 関数名先頭の _ は「内部用、外から呼ばないでね」の慣習。-> dict は戻り値の型ヒント
    """テンプレートに渡す current_user 情報を組み立てる."""
    if user is None:  # 未ログインの場合。get_optional_user が None を返したケース
        return {
            "current_user": None
        }  # テンプレート側で {% if current_user %} で分岐できるよう None を明示
    return {
        "current_user": {  # ORM オブジェクトをそのまま渡さず、必要な値だけ辞書化。テンプレートに余計な属性を露出させない安全策
            "id": user.id,
            "username": user.username,
            "is_admin": user.is_admin,  # 管理者フラグ。テンプレートで「削除ボタン表示」など権限分岐に使う
        },
    }


@app.get("/")  # GET / にアクセスが来た時に呼ばれる関数を登録するデコレーター。トップページ
def index(
    request: Request,  # FastAPI が自動で渡す。テンプレートに渡すと url_for などが使える
    db: Session = Depends(
        get_db
    ),  # Depends は依存性注入。get_db が yield した DB セッションを受け取る。リクエスト終了時に自動 close
    current_user=Depends(
        get_optional_user
    ),  # 「optional」=ログイン中なら User、未ログインなら None。/ はゲストでも見られるので必須にしない
):
    posts = (
        db.query(Post).order_by(desc(Post.created_at)).all()
    )  # 全投稿を作成日時の降順（新→古）で取得。.all() でリストとして確定
    like_counts = {  # 投稿 ID → いいね数 の辞書を作る
        post.id: db.query(Like)
        .filter(Like.post_id == post.id)
        .count()  # 各投稿について、紐付く Like 行数を数える
        for post in posts  # ※ 投稿数だけクエリが走る (N+1 問題)。本番規模では JOIN 集計に置き換えるのが定石
    }
    return templates.TemplateResponse(
        "index.html",  # テンプレートファイル名。templates/index.html が描画される
        {  # テンプレートに渡すコンテキスト辞書。{{ posts }} などで参照される
            "request": request,  # Jinja2Templates では request の受け渡しが必須
            "posts": posts,
            "like_counts": like_counts,
            **_build_user_context(current_user),  # ** で辞書展開。current_user キーがマージされる
        },
    )


@app.get(
    "/login"
)  # ログインフォーム表示専用。実際のログイン処理は POST /auth/login（routers/auth.py）が担当
def login_page(request: Request, current_user=Depends(get_optional_user)):
    return templates.TemplateResponse(
        "login.html",  # フォーム HTML。送信先は /auth/login
        {
            "request": request,
            **_build_user_context(current_user),
        },  # ヘッダー表示のため current_user は渡しておく
    )


@app.get("/register")  # 新規登録フォーム表示。POST 処理は routers/auth.py 側
def register_page(request: Request, current_user=Depends(get_optional_user)):
    return templates.TemplateResponse(
        "register.html",
        {"request": request, **_build_user_context(current_user)},
    )


@app.get(
    "/upload"
)  # 投稿フォーム表示。ログイン必須にしていないが、テンプレ側で current_user の有無を見て案内分岐する想定
def upload_page(request: Request, current_user=Depends(get_optional_user)):
    return templates.TemplateResponse(
        "upload.html",
        {"request": request, **_build_user_context(current_user)},
    )


@app.get("/search")  # 検索結果ページ。?search_query=xxx の形でクエリ文字列が渡る
def search_page(
    request: Request,
    search_query: str = "",  # 関数引数 = クエリパラメータ。型 str + デフォルト値で「省略可・初期値空文字」になる
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    search_keyword = search_query.strip()[
        :100
    ]  # 前後空白除去 + 100 文字に切り詰め。長すぎる入力で DB に負荷を掛けない防御策
    posts = (
        db.query(Post)
        .filter(
            Post.title.ilike(f"%{search_keyword}%")
        )  # ilike は大文字小文字を区別しない LIKE。% は任意文字列のワイルドカード（部分一致）
        .order_by(desc(Post.created_at))  # 新しい順に並べる
        .all()
    )
    return templates.TemplateResponse(
        "search_results.html",
        {
            "request": request,
            "posts": posts,
            "search_keyword": search_keyword,  # 検索ボックスに入力値を再表示するためテンプレに渡す
            **_build_user_context(current_user),
        },
    )


@app.get("/post/{id}")  # {id} はパスパラメータ。/post/42 のように URL の一部として値が渡る
def post_page(
    request: Request,
    id: int,  # パスパラメータと同名の引数で受け取る。型 int 指定で自動的に整数変換 + 不正値は 422 エラー
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    post = (
        db.query(Post).filter(Post.id == id).first()
    )  # .first() は最初の1件 or None。.one() は0件/複数件で例外を投げる別物
    if not post:  # post が None の場合（投稿が削除済み or 存在しない id 指定）
        raise HTTPException(
            status_code=404, detail="投稿が見つかりません"
        )  # FastAPI は HTTPException を捕まえて適切なレスポンスに変換してくれる
    like_count = db.query(Like).filter(Like.post_id == id).count()  # この投稿に紐付くいいね数
    return templates.TemplateResponse(
        "post.html",
        {
            "request": request,
            "post": post,
            "like_count": like_count,
            **_build_user_context(current_user),
        },
    )


@app.get("/health")  # 死活監視用。ロードバランサや監視ツールが定期的に叩いて生存確認する慣習
def health_check():
    """ヘルスチェックエンドポイント."""
    return {
        "status": "ok"
    }  # 辞書を返すと FastAPI が自動で JSON にしてレスポンス。テンプレートと違って軽量


# ==============================================================================
# エラーハンドリング
# ==============================================================================


@app.exception_handler(
    HTTPException
)  # HTTPException（404, 401 など意図的に発生させる例外）が起きた時の専用ハンドラを登録
async def custom_http_exception_handler(request, exception):
    return await http_exception_handler(
        request, exception
    )  # 今は FastAPI 標準の挙動を呼び出すだけ。将来カスタムログ追加などの拡張ポイントとして残してある


@app.exception_handler(
    RequestValidationError
)  # Pydantic スキーマ検証エラー（リクエストボディが期待形式と違う等）専用ハンドラ
async def custom_validation_exception_handler(request, exception):
    return await request_validation_exception_handler(request, exception)  # こちらも標準実装に委譲


@app.exception_handler(Exception)  # 上記以外の「想定外の」全例外をキャッチする最後の砦
async def general_exception_handler(request, exception):
    log = get_logger("app.unhandled")  # 未処理例外専用のロガー名で記録。後で grep しやすい
    log.exception(
        "unhandled_exception", path=str(request.url)
    )  # log.exception はトレースバックも自動で含める。原因調査に必須
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error"
        },  # 内部のエラー詳細はクライアントに返さない（情報漏洩防止）。詳細はサーバ側ログでのみ確認
    )

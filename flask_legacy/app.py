"""アプリケーションの起動・構成を行うエントリーポイント。

このファイルでは以下の責務を担います。

- Flask アプリケーションの生成と設定
- CSRF 保護の有効化
- Flask-Login の初期化
- ルート関数（エンドポイント）の登録
- データベースとアップロードディレクトリの初期化・マイグレーション

ルーティング自体のロジックは `routes.py` / `auth.py` / `search.py` に分割してあり、
ここではそれらを組み合わせてアプリを完成させる役割を担っています。
"""

import os

from auth import (
    login,
    login_manager,
    logout,
    register,
)
from db import (
    DATABASE_PATH,
    UPLOADS_DIR,
    close_db,
    ensure_likes_index,
    ensure_posts_has_body,
    init_db,
)
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from routes import delete, home, like, post, upload
from search import search


def create_app():
    """Flask アプリケーションを生成して設定を適用する。"""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY"
    )  # 初期段階ではdev-secretも指定されていたがセキュリティ的な理由で削除.envファイルにSECRET_KEYを記載

    # CSRF トークンの有効化
    CSRFProtect(app)

    # ログイン管理を初期化し、リクエスト終了時に DB をクローズするよう登録
    login_manager.init_app(app)
    app.teardown_appcontext(close_db)

    # 各ルートを登録（テンプレートや他ファイルからの url_for() に影響する）
    app.add_url_rule(
        "/register",
        endpoint="register",
        view_func=register,
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/login",
        endpoint="login",
        view_func=login,
        methods=["GET", "POST"],
    )
    app.add_url_rule("/logout", endpoint="logout", view_func=logout)

    app.add_url_rule(
        "/upload",
        endpoint="upload",
        view_func=upload,
        methods=["GET", "POST"],
    )
    app.add_url_rule("/", endpoint="home", view_func=home)
    app.add_url_rule("/post/<int:id>", endpoint="post", view_func=post)
    app.add_url_rule(
        "/like/<int:id>",
        endpoint="like",
        view_func=like,
        methods=["POST"],
    )
    app.add_url_rule(
        "/delete/<int:id>",
        endpoint="delete",
        view_func=delete,
        methods=["POST"],
    )
    app.add_url_rule("/search", endpoint="search", view_func=search, methods=["GET"])

    # アップロード先ディレクトリを作成（存在しない場合）
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    # データベースファイルが存在しない場合はスキーマを作成
    if not os.path.exists(DATABASE_PATH):
        init_db()

    # マイグレーション・運用時の整合性を保つ補助処理
    ensure_likes_index()
    ensure_posts_has_body()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)

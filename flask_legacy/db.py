"""ポートフォリオ Web アプリのデータベースヘルパー。

このモジュールはアプリケーションで使う SQLite データベースを初期化し、
リクエストごとの接続管理と簡単なマイグレーションを提供します。

データベースはプロジェクトルートにある "database.db" という単一のファイルです。
Flask のリクエストライフサイクルと連携して、
各リクエストごとに同じ接続を使い、リクエスト終了時に閉じるようにしています。
"""

import os
import sqlite3

from flask import g

# -----------------------------------------------------------------------------
# 定数（設定値）
# -----------------------------------------------------------------------------

# SQLite のデータベースファイルのパス。存在しなければ起動時に自動生成されます。
DATABASE_PATH = "database.db"

# 画像アップロード先ディレクトリ。存在しなければアプリ起動時に作成されます。
UPLOADS_DIR = os.path.join("static", "uploads")


# -----------------------------------------------------------------------------
# リクエスト単位の接続管理
# -----------------------------------------------------------------------------


def get_db():
    """現在のリクエストで使う SQLite 接続を取得（なければ作成）。

    Flask にはリクエスト単位で共有できる ``g`` というオブジェクトがあります。
    この関数は ``g`` に接続を保持しておき、同じリクエスト内では
    何度呼ばれても同じ接続を再利用します。

    また、``row_factory`` を ``sqlite3.Row`` に設定することで、
    クエリ結果を ``row['username']`` のようにカラム名でアクセスできます。
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None):
    """リクエスト終了時にデータベース接続を閉じる。"""
    # Flask の teardown_appcontext に登録しておくことで、例外発生時でも
    # 確実に実行されるようにしています。
    database = g.pop("db", None)
    if database is not None:
        database.close()


# -----------------------------------------------------------------------------
# スキーマ初期化（最初にデータベースを作るとき）
# -----------------------------------------------------------------------------


def init_db():
    """初回起動時に必要なテーブルを作成する。"""
    database_connection = sqlite3.connect(DATABASE_PATH)
    cursor = database_connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            filename TEXT,
            body TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            post_id INTEGER
        )
    """)

    database_connection.commit()
    database_connection.close()


# -----------------------------------------------------------------------------
# スキーマ変更・マイグレーション用の補助関数
# -----------------------------------------------------------------------------


def ensure_likes_index():
    """いいねの重複を防ぐためのユニークインデックスを作成する。

    likes テーブルでは、同じユーザーが同じ投稿に対して複数回いいね
    できないようにする必要があります。

    この関数は ``IF NOT EXISTS`` を使っているので、何度呼んでも安全です。
    """
    database_connection = sqlite3.connect(DATABASE_PATH)
    cursor = database_connection.cursor()
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS index_likes_user_post ON likes(user_id, post_id)",
    )
    database_connection.commit()
    database_connection.close()


def ensure_posts_has_body():
    """Posts テーブルに body カラムがなければ追加する。

    以前のバージョンで body カラムが存在しない可能性があるため、
    アプリ起動時にこの関数を呼んで列の有無をチェックします。

    既に存在する場合は何もしないので、何度呼んでも安全です。
    """
    database_connection = sqlite3.connect(DATABASE_PATH)
    cursor = database_connection.cursor()
    cursor.execute("PRAGMA table_info(posts)")
    columns = cursor.fetchall()
    column_names = [column_info[1] for column_info in columns]
    if "body" not in column_names:
        cursor.execute("ALTER TABLE posts ADD COLUMN body TEXT")
        database_connection.commit()
    database_connection.close()

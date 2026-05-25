"""FastAPI 用のデータベース管理モジュール。

SQLAlchemy で SQLite/PostgreSQL を扱う。
スキーマ変更は Alembic 経由で行うこと（init_db は dev 用の補助）。

【このファイルの役割】
- DBへの接続設定(engine) と セッション工場(SessionLocal) を作る。
- ORMモデル(User/Post/Like) を定義し、Pythonクラス ⇔ DBテーブルを対応付ける。
- リクエストごとに使うDBセッション払い出し関数(get_db) を提供する。

【なぜスキーマ層(schemas.py)と分けるか】
- db.py の役割: DBに保存する全項目を定義する(password ハッシュ・内部フラグ等も含む)。
- schemas.py の役割: APIで受け取る/返す項目だけを定義する。
- 両者を分けないと、DBの列を増やしただけでAPIレスポンスにも勝手に出てしまい、
  password ハッシュなど見せてはいけない情報が漏れる事故につながる。
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

# 【なぜ check_same_thread が必要か】
# SQLite はデフォルトで「接続を作ったスレッド以外からの利用」を拒否する。
# FastAPIは複数スレッドでリクエストを捌くため、この制限を外さないとエラーになる。
# PostgreSQL等は元々マルチスレッド対応なので、この引数を渡してはいけない（未知引数として弾かれる）。
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# 【engine とは】
# DBへの「接続プール本体」。アプリ全体で1つだけ作り、使い回す。
# echo=False は SQLログ出力を抑制（True にするとデバッグ時に発行SQLが見える）。
engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=False,
)

# 【SessionLocal とは】
# DBセッション(=トランザクションの作業領域) を作る「工場」。
# - autocommit=False: 明示的に commit() を呼ばない限り保存しない（事故防止）。
# - autoflush=False:  クエリ発行時に自動でPython側変更をDBへ送らない
#   （意図しない中途半端な書き込みを防ぐ）。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 【Base とは】
# 全ORMモデルが継承する共通の親クラス。
# Base のサブクラスを定義すると SQLAlchemy がそれをテーブルとして認識する。
Base = declarative_base()


# ==============================================================================
# モデル定義
# ==============================================================================


class User(Base):
    """ユーザーテーブル."""

    __tablename__ = "users"

    # 【各列の意図】
    # - id: 主キー。index=True は検索高速化のためインデックスを張る指示。
    # - username: unique=True で同名登録を禁止。index でログイン時の検索を高速化。
    #   nullable=False により NULL 登録(=未入力)もDBレベルで弾く。
    # - password: 平文ではなく bcrypt ハッシュを格納する。長さ255は余裕を持たせた値。
    # - is_admin: 認可判定をこのフラグに集約することで、
    #   「username == 'admin' 文字列で判定」というなりすまし可能な実装を排除。
    #   server_default="0" はDB側のデフォルト値。既存行の移行時にも安全。
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    # 管理者フラグ。username 文字列ではなくこのフラグで認可判定する
    is_admin = Column(Boolean, nullable=False, default=False, server_default="0")


class Post(Base):
    """投稿テーブル."""

    __tablename__ = "posts"

    # 【各列の意図】
    # - user_id: ForeignKey により users.id との参照整合性をDBが保証。
    #   存在しないユーザーIDで投稿が作られる事故を防ぐ。
    # - title: 必須。max 255 は VARCHAR(255) の慣習＋schemas.py の制限と一致させる。
    # - filename: 画像なし投稿も許すので nullable=True。
    #   実体は static/uploads/ 配下に保存されたファイル名(UUID)。
    # - body: 本文。長文の可能性に備えて Text 型(SQLite/Postgres 共に長さ無制限)。
    # - created_at:
    #   * default に lambda を使う理由: モジュール読込時刻ではなく「行作成時刻」を入れるため
    #     （関数を渡すと毎回呼び出される; 値を直接渡すと固定値になってしまう）。
    #   * timezone.utc を使う理由: サーバTZに依存しないUTCで保存し、
    #     表示時にローカル変換するのが時刻データの正攻法。
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
    # 【なぜ UNIQUE 制約を DB レベルで貼るか】
    # アプリ側のチェック「既に押してないか?」だけでは、
    # 同時押下(race condition) で2件insertされる可能性がある。
    # DBの複合UNIQUE で「(user_id, post_id) の組合せは1行だけ」を強制し、
    # 二重いいねを物理的に不可能にする。
    __table_args__ = (UniqueConstraint("user_id", "post_id", name="uq_likes_user_post"),)

    # 【なぜ id を別途持つか】
    # (user_id, post_id) の複合主キーでも論理上は同じだが、
    # サロゲートキー(連番id) があると個別の行をURLや内部処理で参照しやすい。
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)


# ==============================================================================
# ユーティリティ関数
# ==============================================================================


def get_db():
    """リクエストごとのセッションを取得."""
    # 【なぜ yield を使うジェネレータにするか】
    # FastAPI の Depends() は「yield 前で前処理 / yield 後で後始末」を自動で実行する仕組み。
    # この形にすることで、エンドポイント実行後に必ず db.close() が走り、
    # 接続リーク(プール枯渇) を防げる。例外が出ても finally で必ずクローズされる。
    #
    # 【なぜリクエストごとに新セッションか】
    # セッションを使い回すと、別リクエストの未コミット変更が混ざる、
    # トランザクション境界が曖昧になる等の問題が起きる。
    # 「1リクエスト = 1セッション = 1トランザクション」が原則。
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# スキーマ初期化は Alembic マイグレーション (`alembic upgrade head`) で行う。
# 起動時には `app.core.migrate.run_migrations` 経由で自動実行される。
# 【なぜ Base.metadata.create_all を使わないか】
# create_all は「現状のモデル定義から一発でテーブルを作る」が、列追加や型変更などの
# 差分マイグレーションができない。本番運用では Alembic で履歴管理するのが必須。


# アップロード先ディレクトリ設定
# 【なぜ定数化するか】
# パス文字列を複数箇所にハードコードすると変更時の漏れが起きる。
# 1箇所に集約することで「保存場所を変えたい」が import 修正だけで済む。
UPLOADS_DIR = os.path.join("static", "uploads")


def setup_uploads_dir():
    """アップロード先ディレクトリを作成（存在しない場合）."""
    # 【なぜ exist_ok=True か】
    # 既にディレクトリがあると makedirs は例外を投げる。
    # 起動毎に呼ばれる関数なので、既存時は黙って通すのが正しい挙動。
    os.makedirs(UPLOADS_DIR, exist_ok=True)

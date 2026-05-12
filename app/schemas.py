"""Pydantic スキーマ定義。

API のリクエスト/レスポンスのバリデーションに使用します。

【なぜスキーマ層が必要か】
- DBモデル(db.py)をそのまま外部に晒すと、内部構造の変更がAPI仕様の破壊につながる。
- 入力(Request)はクライアントの自由入力なので「型・長さ・形式」を必ず検証する必要がある。
- 出力(Response)はパスワードハッシュなど見せてはいけないフィールドを除外する役割もある。
- このため「DBモデルとは別に」入出力専用のクラスをここに定義する。
"""

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# ==============================================================================
# ユーザー関連スキーマ
# ==============================================================================


# 【なぜ予約名が必要か】
# このアプリは username == "admin" を管理者判定に使う実装が一部に残るため、
# 一般ユーザーが "admin" 名で登録できると権限のなりすましが可能になる。
# 似た紛らわしい名前(administrator/root/system)もまとめて禁止し、誤認を防ぐ。
RESERVED_USERNAMES = {
    "admin",
    "administrator",
    "root",
    "system",
}  # 予約ユーザー名（大文字小文字無視）


class UserRegister(BaseModel):
    """ユーザー登録リクエストスキーマ."""

    # 【なぜ Field で min/max を縛るか】
    # - min_length=1: 空文字登録を防ぐ（空 username はDB上ユニーク扱いがブレる原因）。
    # - max_length=255: DBの VARCHAR(255) と整合させ、長すぎる入力でDBエラーになる前に弾く。
    # - password の min_length=8: 短すぎるパスワードは総当たりに弱いため最低長を強制。
    # - password の max_length=128: bcrypt の入力上限(72byte)対策＋極端に長い入力で
    #   ハッシュ計算がDoS化するのを防ぐ。
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
        # 【なぜ複雑度ルールが必要か】
        # 長さだけでは "aaaaaaaa" のような弱いパスワードを許してしまう。
        # 「英数字 + 記号」の混在を強制することで辞書攻撃に対する強度を底上げする。

        # 1) 半角の表示可能ASCII(\x21-\x7E)のみ許可。全角や制御文字・空白を排除し、
        #    入力ミスや見えない文字によるログイン不能を防ぐ。
        if not re.match(r"^[\x21-\x7E]+$", password):
            raise ValueError(
                "パスワードは8文字以上・半角英数字・記号を1つ以上含むようにしてください",
            )
        # 2) 英数字を最低1文字含む。記号だけのパスワードを禁止。
        if not re.search(r"[a-zA-Z0-9]", password):
            raise ValueError(
                "パスワードは8文字以上・半角英数字・記号を1つ以上含むようにしてください",
            )
        # 3) 記号を最低1文字含む。英数字のみのパスワードを禁止。
        if not re.search(r"[\x21-\x2F\x3A-\x40\x5B-\x60\x7B-\x7E]", password):
            raise ValueError(
                "パスワードは8文字以上・半角英数字・記号を1つ以上含むようにしてください",
            )
        return password


class UserLogin(BaseModel):
    """ログインリクエストスキーマ."""

    # 【なぜ登録用と分けるか】
    # ログインは「過去に登録された値」を照合するだけなので、現在のパスワードルール
    # (8文字以上・記号必須など)を適用してはいけない。ルールを後から強化した時に
    # 既存ユーザーがログインできなくなるのを防ぐため、検証は最小限に留める。
    username: str
    password: str


class UserResponse(BaseModel):
    """ユーザー情報レスポンススキーマ."""

    # 【なぜ password を含めないか】
    # レスポンス用スキーマに password(ハッシュ含む)を入れると、
    # APIレスポンスで認証情報が漏洩する致命的な事故になる。
    # 「外に出して良いフィールドだけ」をここに列挙するのが安全策。
    id: int
    username: str

    class Config:
        # 【なぜ from_attributes が必要か】
        # SQLAlchemyのORMオブジェクト(属性アクセス: user.id)を
        # そのまま Pydantic に渡して変換できるようにする設定。
        # これがないと dict 化してから渡す手間が必要になる。
        from_attributes = True


# ==============================================================================
# 投稿関連スキーマ
# ==============================================================================


class PostCreate(BaseModel):
    """投稿作成リクエストスキーマ."""

    # 【なぜ長さ制限を置くか】
    # - title: 必須(...) かつ DB の VARCHAR(255) と整合。空タイトルは一覧表示が崩れる。
    # - body: 任意。140文字上限はTwitter的UX設計＋ストレージ・表示崩れ抑制が目的。
    #   None も許容するのは「画像だけ投稿したい」ケースに対応するため。
    title: str = Field(..., min_length=1, max_length=255)
    body: str | None = Field(default="", max_length=140)


class PostResponse(BaseModel):
    """投稿レスポンススキーマ."""

    # 【なぜ作成用(PostCreate)と分けるか】
    # 作成時にクライアントが送るのは title/body だけだが、
    # レスポンスには id・user_id・created_at などサーバ側で付与した情報も含める必要がある。
    # 入力と出力で必要なフィールドが異なるので別クラスに分けるのが基本形。
    id: int
    user_id: int
    title: str
    filename: str | None = None  # 画像未添付の投稿もあるため Optional
    body: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True  # ORM オブジェクトから直接変換可能にする


class PostWithLikes(PostResponse):
    """いいね数を含む投稿レスポンススキーマ."""

    # 【なぜ PostResponse と別クラスにするか】
    # いいね数は集計クエリが必要で、毎回計算するとコストになる。
    # 「いいね数が必要な画面(一覧・詳細)」だけこのクラスを使い、
    # 不要な画面では PostResponse を使い分けることで無駄な集計を避けられる。
    like_count: int = 0


# ==============================================================================
# いいね関連スキーマ
# ==============================================================================


class LikeResponse(BaseModel):
    """いいね操作レスポンススキーマ."""

    # 【なぜ liked と like_count を両方返すか】
    # - liked: 押下後に「いま自分はいいね済みか」をUIのハート色切替に使う。
    # - like_count: 全体の合計いいね数。連打しても再取得せず画面を即更新できる。
    # この2つを同時に返すことで、クライアントは追加APIを叩かずUI更新が完結する。
    liked: bool
    like_count: int


# ==============================================================================
# 検索関連スキーマ
# ==============================================================================


class SearchResults(BaseModel):
    """検索結果レスポンススキーマ."""

    # 【なぜ list だけ返さず wrapper に包むか】
    # - search_keyword: 検索ワードをエコーバックすることで、
    #   非同期通信の応答が遅れて別ワードと混ざる事故を防げる(画面表示の整合性)。
    # - 将来 total件数 や ページング情報を追加するときに、
    #   トップレベルが list だと破壊的変更になる。dict 形式なら拡張が容易。
    search_keyword: str
    posts: list[PostResponse]


# ==============================================================================
# エラーレスポンススキーマ
# ==============================================================================


class ErrorResponse(BaseModel):
    """エラーレスポンススキーマ."""

    # 【なぜエラー専用スキーマを定義するか】
    # FastAPI のデフォルトでは HTTPException のメッセージは {"detail": "..."} で返る。
    # この形式を明示的にスキーマ化することで、OpenAPI(Swagger UI) 上に
    # 「失敗時のレスポンス形」が型として表示され、クライアント側の実装が楽になる。
    detail: str

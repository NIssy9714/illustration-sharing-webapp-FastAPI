# ポートフォリオ API

FastAPI ベースのポートフォリオ投稿アプリケーション。

---

## 概要

本プロジェクトはシンプルなポートフォリオ投稿 REST API です。
FastAPI と SQLAlchemy を使用した実務寄りの構成になっています。

### 主な機能

- **ユーザー認証**: JWT を **HttpOnly Cookie** に格納（`Authorization: Bearer` 互換）
- **投稿管理**: CRUD 操作（作成・一覧・詳細・削除）
- **画像処理**: Pillow を使用した検証＋サムネイル生成
- **いいね機能**: `UNIQUE(user_id, post_id)` 制約で重複登録を防止したトグル
- **検索機能**: タイトルによる投稿検索
- **レート制限**: `slowapi` で `/auth/*`・`/posts/*` を IP 単位で制限
- **マイグレーション**: Alembic（起動時に自動 `upgrade head`）
- **構造化ログ**: structlog（dev はコンソール、prod は JSON）
- **エラー監視**: Sentry SDK（`SENTRY_DSN` 設定時のみ有効化）

---

## 技術スタック

- **Python 3.10+**
- **FastAPI** … REST API フレームワーク
- **SQLAlchemy 2.x / Alembic** … ORM とマイグレーション
- **Pydantic v2 / pydantic-settings** … バリデーションと環境変数管理
- **PyJWT / bcrypt** … 認証
- **Pillow** … 画像検証・サムネイル
- **slowapi** … レート制限
- **structlog / sentry-sdk** … 構造化ログとエラー監視
- **SQLite**（開発既定）/ **PostgreSQL**（docker-compose の本番想定）

---

## プロジェクト構成

```
portfolio_fastapi/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI アプリケーションエントリーポイント
│   ├── db.py                # SQLAlchemy モデル・データベース設定
│   ├── schemas.py           # Pydantic スキーマ
│   ├── image_service.py     # 画像処理ユーティリティ
│   ├── generate_thumbs.py   # サムネイル一括生成スクリプト
│   ├── core/
│   │   └── __init__.py
│   └── routers/
│       ├── __init__.py
│       ├── auth.py          # 認証エンドポイント
│       ├── posts.py         # 投稿エンドポイント
│       └── search.py        # 検索エンドポイント
├── main.py                  # アプリケーション起動スクリプト
├── requirements.txt         # 依存パッケージ
├── .env                     # 環境変数設定
├── .env.example             # 環境変数テンプレート
├── database.db              # SQLite データベース（自動生成）
├── static/                  # 画像・CSS などの静的ファイル
├── templates/               # HTML テンプレート（HTML UI 用）
├── docker-compose.yml       # Docker Compose 設定
├── Dockerfile               # Docker イメージ定義
└── README.md
```

---

## セットアップ

### 必要要件

- Python 3.10 以上
- pip

### インストール

1. リポジトリをクローン

```bash
git clone <repository-url>
cd portfolio_fastapi
```

2. 仮想環境を作成・有効化

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

3. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

4. 環境変数を設定（.env を編集）

```bash
cp .env.example .env
```

---

## 使用方法

### API サーバー起動

```bash
python main.py
```

または

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

サーバーは `http://localhost:8000` で起動します。

### API ドキュメント

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## API エンドポイント

### 認証関連

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| POST | `/auth/register` | ユーザー登録 |
| POST | `/auth/login` | ログイン |
| POST | `/auth/logout` | ログアウト |

### 投稿関連

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/posts/` | 投稿一覧取得 |
| POST | `/posts/` | 投稿作成（画像アップロード） |
| GET | `/posts/{post_id}` | 投稿詳細取得 |
| DELETE | `/posts/{post_id}` | 投稿削除 |
| POST | `/posts/{post_id}/like` | いいねをトグル |

### 検索関連

| メソッド | エンドポイント | 説明 |
|---------|---------------|------|
| GET | `/search?query=...` | 投稿を検索 |

---

## 認証フロー

JWT（JSON Web Token）ベースのステートレス認証。
保存方法は **HttpOnly Cookie が主** で、`Authorization: Bearer` も互換のため受け付ける。

1. `/auth/login` でログイン
2. サーバーが JWT を発行し、`access_token` Cookie（HttpOnly / SameSite=Lax）にセット。
   API レスポンス本文にも `access_token` を返す
3. ブラウザは以降の同一オリジン要求で自動的に Cookie を送信。
   API クライアントは `Authorization: Bearer <token>` でも認証可能
4. `/auth/logout` で Cookie を削除

### Cookie 設定

| 環境変数 | 役割 | 推奨値 |
|----------|------|--------|
| `COOKIE_SECURE` | HTTPS 限定で送信 | 本番 `true`（dev は `false`） |
| `COOKIE_SAMESITE` | CSRF 対策 | `lax`（同一オリジン構成なら `strict`） |

---

## データベーススキーマ

### users テーブル

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
)
```

### posts テーブル

```sql
CREATE TABLE posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL FOREIGN KEY,
    title VARCHAR(255) NOT NULL,
    filename VARCHAR(255),
    body TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### likes テーブル

```sql
CREATE TABLE likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL FOREIGN KEY,
    post_id INTEGER NOT NULL FOREIGN KEY,
    UNIQUE (user_id, post_id)
)
```

`UNIQUE(user_id, post_id)` により、同一ユーザーから同一投稿への二重いいね登録を DB レベルで防ぐ。

---

## 開発時の注意点

### 環境変数

`.env.example` をコピーして `.env` を作成し編集する：

| 変数 | 説明 |
|------|------|
| `APP_ENV` | `dev` / `prod` / `test` |
| `SECRET_KEY` | JWT 署名鍵。本番は `openssl rand -hex 32` で生成 |
| `DATABASE_URL` | 既定 `sqlite:///./database.db`、Postgres は `postgresql+psycopg://...` |
| `ALLOWED_ORIGINS` | CORS 許可オリジン（カンマ区切り、`*` 不可） |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | Cookie のセキュリティ属性 |
| `SENTRY_DSN` | 任意。設定時のみ Sentry を有効化 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | docker-compose の db サービスで使用 |

本番環境では `SECRET_KEY` がデフォルト値だと起動が拒否される（lifespan 内でガード）。

### データベースマイグレーション

アプリ起動時の lifespan で `alembic upgrade head` を自動実行する
（`APP_ENV=test` ではテスト側がスキーマを直接作成するためスキップ）。

手動実行：

```bash
alembic upgrade head            # 最新へ
alembic downgrade -1            # 1 つ戻す
alembic revision --autogenerate -m "msg"  # モデル変更から雛形を生成
```

---

## Docker での実行

`docker-compose.yml` には `api`（FastAPI）と `db`（PostgreSQL 16）の 2 サービスを定義。
`db` の healthcheck が通ってから `api` が起動し、起動時に自動で `alembic upgrade head` が走る。

```bash
cp .env.example .env       # POSTGRES_PASSWORD / SECRET_KEY を編集
docker compose up --build
```

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- DB（ホスト側ポート公開時）: `postgresql://portfolio:***@localhost:5432/portfolio`

---

## テスト

```bash
pytest
```

---

## レガシーコード

古い Flask 実装は `flask_legacy/` フォルダに保存されています。

---

## ライセンス

MIT

---

## 参考リンク

- [FastAPI 公式ドキュメント](https://fastapi.tiangolo.com/)
- [SQLAlchemy 公式ドキュメント](https://docs.sqlalchemy.org/)
- [Pydantic 公式ドキュメント](https://docs.pydantic.dev/)
- **SQLite** … 学習用途（`database.db` 生成）
- **Pillow** … 画像検証・サムネイル生成

---

## ディレクトリ構成（Structure）

```
.
├── app.py              # エントリーポイント：Flask アプリ生成・ルート登録・DB 初期化
├── auth.py             # 認証処理（登録・ログイン・ログアウト）
├── db.py               # SQLite 接続管理・スキーマ生成・マイグレーション
├── routes.py           # 投稿・いいね・削除などのビジネスロジック
├── search.py           # 検索機能処理
├── image_service.py    # 画像アップロードとサムネイル生成
├── requirements.txt    # 依存パッケージ
├── database.db         # SQLite DB（実行時に生成される場合あり）
├── templates/          # HTML テンプレート（Jinja2）
└── static/             # CSS・アップロード画像（uploads/・thumbs/）
```

---

## 使い方

1. 依存パッケージをインストールする

```bash
pip install -r requirements.txt
```

2. Flask 版アプリを起動する

```bash
python app.py
```

3. ブラウザで `http://localhost:5000/` にアクセスする

---

## FastAPI 版（実務寄り構成）

このリポジトリには、**環境変数で設定を管理**し、**PostgreSQL を前提**にした FastAPI 版（`fastapi_app/`）も同梱しています。
APIキーやパスワード等をコード内に直書きせず、`.env` で注入する前提です。

### 事前準備

- `.env.example` をコピーして `.env` を作成し、値を設定してください（**実値はコミットしない**）

### Docker で起動（おすすめ）

※ Docker がインストールされている環境が必要です。

```bash
docker compose up --build
```

- API: `http://localhost:8000`
- ヘルスチェック: `http://localhost:8000/healthz`
- Swagger UI: `http://localhost:8000/docs`

### ローカル起動（Dockerなし）

```bash
pip install -r requirements.txt
uvicorn fastapi_app.app.main:app --reload --port 8000
```

### マイグレーション（Alembic）

このリポジトリには **初回マイグレーション**（`fastapi_app/migrations/versions/0001_init.py`）を同梱しています。
PostgreSQL を用意して `DATABASE_URL` を設定したうえで、次を実行してください。

```bash
alembic -c fastapi_app/alembic.ini upgrade head
```

（参考）モデルから自動生成したい場合（DBへ接続できる状態が必要）:

```bash
alembic -c fastapi_app/alembic.ini revision --autogenerate -m "init"
alembic -c fastapi_app/alembic.ini upgrade head
```

### 認証API（最低限）

- `POST /auth/register` : ユーザー作成
- `POST /auth/login` : トークン発行（Bearer）

例:

```bash
curl -X POST http://localhost:8000/auth/register ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"test\",\"password\":\"password123\"}"
```

```bash
curl -X POST http://localhost:8000/auth/login ^
  -H "Content-Type: application/json" ^
  -d "{\"username\":\"test\",\"password\":\"password123\"}"
```

---

## テスト（pytest）

FastAPI 版のAPIフロー（登録→ログイン→投稿→いいね→削除）を、SQLiteインメモリDBで自動テストします。

```bash
pip install -r requirements.txt
pytest -q
```

---

## 設計方針（Design Policy）

1. まず動く状態にしてから責務を分離する
2. フレームワークの“魔法”を追いかけすぎず、処理の流れを自分で追えるようにする
3. コメントやドキュメントを充実させ、第三者が理解しやすい状態を保つ

---

## 今後の改善案（TODO）

- 管理者権限の明確化（ロールごとのアクセス制御）
- 本番環境用設定の分離（環境ごとの設定ファイルなど）
- セキュリティ強化（セッション管理、入力バリデーション、CSRF など）
- テスト自動化（ユニットテスト・統合テスト）

---

## 注意事項

本リポジトリは**学習目的**であり、
そのまま本番環境で利用することを想定していません。

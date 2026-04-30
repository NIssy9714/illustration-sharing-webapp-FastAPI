# ポートフォリオ API

FastAPI ベースのイラスト投稿アプリケーション。

---

## 概要

シンプルな投稿型ポートフォリオの REST API + サーバーサイドレンダリング画面。
FastAPI / SQLAlchemy 2.x / Alembic / Pydantic v2 を中心とした、実務寄りの構成で構築している。

### 主な機能

- **ユーザー認証**: JWT を **HttpOnly Cookie** に格納（`Authorization: Bearer` 互換）
- **投稿管理**: CRUD 操作（作成・一覧・詳細・削除）
- **画像処理**: Pillow を使った検証＋サムネイル自動生成
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
- **PostgreSQL 16**（Docker 既定・本番想定）/ **SQLite**（ローカル試用・テスト用フォールバック）

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
│   │   ├── config.py        # 設定（pydantic-settings）
│   │   ├── limiter.py       # slowapi レート制限
│   │   ├── logging.py       # structlog 設定
│   │   └── migrate.py       # 起動時 Alembic 実行
│   └── routers/
│       ├── auth.py          # 認証エンドポイント
│       ├── posts.py         # 投稿エンドポイント
│       └── search.py        # 検索エンドポイント
├── alembic/                 # マイグレーションスクリプト
│   ├── env.py
│   └── versions/
├── alembic.ini
├── templates/               # Jinja2 テンプレート（SSR ページ）
├── static/                  # CSS・アップロード画像（uploads/・thumbs/）
├── tests/                   # pytest 統合テスト
├── main.py                  # アプリ起動スクリプト（uvicorn ラッパー）
├── pyproject.toml
├── requirements.txt
├── .env.example             # 環境変数テンプレート
├── docker-compose.yml       # api + db（PostgreSQL 16）
├── Dockerfile
└── README.md
```

---

## セットアップ

クローンしたら `.env.example` を `.env` にコピーして `SECRET_KEY` 等を編集（実値はコミットしない）。

```bash
git clone https://github.com/NIssy9714/illustration-sharing-webapp-FastAPI.git
cd illustration-sharing-webapp-FastAPI
cp .env.example .env
```

起動方法は **Docker（推奨）** と **ローカル直接起動** の 2 通り。

### 1. Docker で起動（推奨）

PostgreSQL を含むフルスタックがそのまま立ち上がる。本番想定の構成で動作確認できる。

```bash
docker compose up --build
```

詳細は [Docker での実行](#docker-での実行) 参照。

### 2. ローカルで起動（SQLite フォールバック）

Docker 不要。`DATABASE_URL` 未設定なら SQLite が自動で `database.db` を生成する。手早く触りたい場合向け。

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows（macOS/Linux: source .venv/bin/activate）
pip install -r requirements.txt
python main.py
```

サーバーは `http://localhost:8000` で起動する。

### 画面（SSR）

| パス | 内容 |
|------|------|
| `/` | 投稿一覧 |
| `/login` / `/register` | ログイン・登録 |
| `/upload` | 投稿作成 |
| `/post/{id}` | 投稿詳細 |
| `/search` | 検索結果 |
| `/health` | ヘルスチェック |

### API ドキュメント

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## API エンドポイント

### 認証

| メソッド | パス | 説明 |
|---------|------|------|
| POST | `/auth/register` | ユーザー登録 |
| POST | `/auth/login` | ログイン（JWT 発行 → Cookie + レスポンス本文） |
| POST | `/auth/logout` | ログアウト（Cookie 削除） |

### 投稿

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/posts/` | 投稿一覧取得 |
| POST | `/posts/` | 投稿作成（画像アップロード） |
| GET | `/posts/{post_id}` | 投稿詳細取得 |
| DELETE | `/posts/{post_id}` | 投稿削除 |
| POST | `/posts/{post_id}/like` | いいねトグル |

### 検索

| メソッド | パス | 説明 |
|---------|------|------|
| GET | `/api/search?query=...` | 投稿をタイトル検索（JSON API） |

> 画面用の検索ページは `/search`（SSR）。JSON API は `/api/search` に分離している。

### サンプルリクエスト

```bash
# ユーザー登録
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"password123"}'

# ログイン（access_token を Cookie・レスポンス両方で受け取る）
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"test","password":"password123"}'
```

---

## 認証フロー

JWT（JSON Web Token）ベースのステートレス認証。
保存方法は **HttpOnly Cookie が主**で、`Authorization: Bearer` も互換のため受け付ける。

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

### users

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
)
```

### posts

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

### likes

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

## 環境変数

`.env.example` をコピーして `.env` を作成し編集する：

| 変数 | 説明 |
|------|------|
| `APP_ENV` | `dev` / `prod` / `test` |
| `SECRET_KEY` | JWT 署名鍵。本番は `openssl rand -hex 32` で生成 |
| `DATABASE_URL` | Docker は `postgresql+psycopg://...`（compose で自動設定）、ローカル既定は `sqlite:///./database.db` |
| `ALLOWED_ORIGINS` | CORS 許可オリジン（カンマ区切り、`*` 不可） |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | Cookie のセキュリティ属性 |
| `SENTRY_DSN` | 任意。設定時のみ Sentry を有効化 |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | docker-compose の db サービスで使用 |

本番環境では `SECRET_KEY` がデフォルト値だと起動が拒否される（lifespan 内でガード）。

---

## マイグレーション

アプリ起動時の lifespan で `alembic upgrade head` を自動実行する
（`APP_ENV=test` ではテスト側がスキーマを直接作成するためスキップ）。

手動実行：

```bash
alembic upgrade head                       # 最新へ
alembic downgrade -1                       # 1 つ戻す
alembic revision --autogenerate -m "msg"   # モデル変更から雛形を生成
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
- ヘルスチェック: `http://localhost:8000/health`
- DB（ホスト側ポート公開時）: `postgresql://portfolio:***@localhost:5432/portfolio`

---

## テスト

統合テストはインメモリ SQLite を使用し、登録 → ログイン → 投稿 → いいね → 削除の API フローを検証する。

```bash
pytest          # フル
pytest -q       # 簡易出力
```

---

## 設計方針

1. まず動く状態にしてから責務を分離する
2. フレームワークの "魔法" を追いかけすぎず、処理の流れを自分で追えるようにする
3. コメント・ドキュメントを充実させ、第三者が理解しやすい状態を保つ
4. **環境別 DB 戦略** — 本番/Docker は PostgreSQL、ローカル試用とテストは SQLite。`DATABASE_URL` 一本で切替可能とし、Alembic は両方対応（`render_as_batch` で SQLite の ALTER 制約を回避）

---

## 今後の改善案（TODO）

- 管理者権限の明確化（ロールごとのアクセス制御）
- フロントエンドの SPA 化（現状は Jinja2 SSR）
- E2E テスト導入（現状は API 統合テストのみ）
- 画像配信を CDN / S3 互換ストレージへ切り出し

---

## 注意事項

本リポジトリは **学習目的** であり、そのまま本番環境で利用することは想定していない。

---

## 参考リンク

- [FastAPI 公式ドキュメント](https://fastapi.tiangolo.com/)
- [SQLAlchemy 公式ドキュメント](https://docs.sqlalchemy.org/)
- [Pydantic 公式ドキュメント](https://docs.pydantic.dev/)
- [Alembic 公式ドキュメント](https://alembic.sqlalchemy.org/)

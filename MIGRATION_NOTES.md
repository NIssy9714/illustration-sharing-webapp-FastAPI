## FastAPI への統一完了

### 実施内容

このフォルダは Flask と FastAPI が混在していた状態から、**完全に FastAPI に統一されました**。

### 変更の主要ポイント

1. **データベースレイヤーの統一**
   - SQLAlchemy ORM を使用（Flask-SQLAlchemy ではなく）
   - SQLite データベースは互換性維持
   - モデル定義: `app/db.py`

2. **認証メカニズムの変更**
   - 旧: Flask-Login セッションベース
   - 新: JWT ベースのトークン認証
   - 実装: `app/routers/auth.py`

3. **API エンドポイント**
   - Flask ビュー関数から FastAPI ルーターに変換
   - RESTful API 設計に統一
   - ルーター分割:
     - `app/routers/auth.py` - 認証
     - `app/routers/posts.py` - 投稿管理
     - `app/routers/search.py` - 検索

4. **ファイル組織**
   ```
   app/
   ├── main.py           # FastAPI アプリケーション
   ├── db.py             # SQLAlchemy モデル・接続管理
   ├── schemas.py        # Pydantic バリデーションスキーマ
   ├── image_service.py  # 画像処理ユーティリティ
   ├── generate_thumbs.py # サムネイル生成
   ├── core/             # コア設定
   └── routers/          # API ルーター
       ├── auth.py
       ├── posts.py
       └── search.py
   ```

5. **レガシーコード**
   - 古い Flask 実装は `flask_legacy/` フォルダに保存
   - 参考用に保持

6. **Docker 対応**
   - `Dockerfile` - FastAPI に対応
   - `docker-compose.yml` - SQLite ベースの簡潔な設定に変更

### 技術的な改善

- **スケーラビリティ**: REST API として複数クライアント対応
- **セキュリティ**: JWT トークンベース認証
- **バリデーション**: Pydantic で厳密なスキーマ検証
- **ドキュメント**: Swagger UI (`/docs`) で自動 API ドキュメント生成
- **非同期対応**: FastAPI の async/await サポート

### 実行方法

```bash
# 依存パッケージをインストール
pip install -r requirements.txt

# アプリケーション起動
python main.py

# または uvicorn で直接起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### API 確認

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI スキーマ: `http://localhost:8000/openapi.json`

### 注意事項

- テンプレート (`templates/`) はまだ Flask 用
- 本アプリケーションは REST API のため、フロントエンド（SPA）は別途開発が必要
- 本番環境では `.env` ファイルの `SECRET_KEY` を変更してください

---

**完成日**: 2026-04-24
**ステータス**: 実務寄り FastAPI 実装完了

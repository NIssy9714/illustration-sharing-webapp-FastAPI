"""API 統合テスト（TestClient 経由）。

設計方針:
- 1 テスト 1 振る舞い。Arrange / Act / Assert を分けて読みやすくする。
- セッションスコープの共有 client を使うため、各テストで:
    * fresh_client = client.__class__(client.app)  を作って Cookie 持ち越しを断つ
    * username はテストごとに固有値（ヘルパー _register_and_login が UUID で生成）

ここで扱うのは「正常系の通し動作」と「基本的な拒否ケース」。
JWT 改ざんなど攻撃系は test_auth_security.py 側で扱う。
"""

from __future__ import annotations

import uuid

# ============================================================
# ヘルパー
# ============================================================


def _new_client(client):
    """Cookie やヘッダーを引き継がない、まっさらな TestClient を作る."""
    return client.__class__(client.app)


def _register_and_login(client, *, username: str | None = None):
    """新規ユーザーを登録（=自動ログイン）した状態の (client, username, token) を返す.

    username 未指定なら UUID で生成（他テストとの衝突を防ぐ）。
    """
    fresh_client = _new_client(client)
    unique_username = username or f"u_{uuid.uuid4().hex[:10]}"
    response = fresh_client.post(
        "/auth/register",
        json={"username": unique_username, "password": "password123!"},
    )
    assert response.status_code == 201, response.text
    return fresh_client, unique_username, response.json()["access_token"]


# ============================================================
# ヘルスチェック
# ============================================================


def test_health(client):
    """/health は無認証で 200 と status:ok を返す."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ============================================================
# 認証フロー
# ============================================================


def test_register_returns_token_and_sets_cookie(client):
    """登録成功時: access_token を返し、HttpOnly Cookie もセットする."""
    fresh_client = _new_client(client)
    username = f"reg_{uuid.uuid4().hex[:10]}"

    response = fresh_client.post(
        "/auth/register",
        json={"username": username, "password": "password123!"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["username"] == username
    assert "access_token" in body
    assert fresh_client.cookies.get("access_token") is not None


def test_login_returns_token_for_existing_user(client):
    """既存ユーザーが正しい資格情報でログインすると access_token が返る."""
    _, username, _ = _register_and_login(client)

    fresh_client = _new_client(client)
    response = fresh_client.post(
        "/auth/login",
        json={"username": username, "password": "password123!"},
    )

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_logout_clears_cookie(client):
    """ログアウト後は Cookie が削除されている."""
    fresh_client, _, _ = _register_and_login(client)
    # ログイン状態の確認
    assert fresh_client.cookies.get("access_token") is not None

    response = fresh_client.post("/auth/logout")

    assert response.status_code == 200
    # Cookie が消える（または空文字になる）
    assert not fresh_client.cookies.get("access_token")


def test_unauthenticated_post_create_returns_401(client):
    """Cookie・Bearer なしで投稿作成しようとすると 401."""
    fresh_client = _new_client(client)
    response = fresh_client.post("/posts/", data={"title": "x"})
    assert response.status_code == 401


# ============================================================
# 投稿の CRUD
# ============================================================


def test_create_post_succeeds_when_authenticated(client):
    """ログイン済みユーザーは投稿を作成できる."""
    fresh_client, _, _ = _register_and_login(client)

    response = fresh_client.post(
        "/posts/",
        data={"title": "hello", "body": "本文"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "hello"
    assert "id" in body


def test_created_post_appears_in_listing(client):
    """作成した投稿が GET /posts/ の一覧に現れる."""
    fresh_client, _, _ = _register_and_login(client)
    created = fresh_client.post("/posts/", data={"title": "list_check"}).json()

    response = fresh_client.get("/posts/")

    assert response.status_code == 200
    assert any(post["id"] == created["id"] for post in response.json())


def test_delete_post_returns_204_and_subsequent_get_is_404(client):
    """投稿者本人の削除は 204、削除後の GET は 404."""
    fresh_client, _, _ = _register_and_login(client)
    post_id = fresh_client.post("/posts/", data={"title": "to_delete"}).json()["id"]

    delete_response = fresh_client.delete(f"/posts/{post_id}")
    assert delete_response.status_code == 204

    get_response = fresh_client.get(f"/posts/{post_id}")
    assert get_response.status_code == 404


# ============================================================
# いいねの仕様
# ============================================================


def test_like_toggle_updates_state_and_count(client):
    """いいねは ON → OFF を繰り返すと state と count が連動する（Bearer 経由）."""
    fresh_client, _, token = _register_and_login(client)
    auth_headers = {"Authorization": f"Bearer {token}"}
    post_id = fresh_client.post("/posts/", data={"title": "likeable"}).json()["id"]

    # 1 回目: ON
    on_response = fresh_client.post(f"/posts/{post_id}/like", headers=auth_headers)
    assert on_response.status_code == 200
    assert on_response.json() == {"liked": True, "like_count": 1}

    # 2 回目: OFF
    off_response = fresh_client.post(f"/posts/{post_id}/like", headers=auth_headers)
    assert off_response.json() == {"liked": False, "like_count": 0}


def test_like_unique_constraint_no_duplicate_rows(client):
    """同一ユーザー×同一投稿のいいねが DB に重複登録されない（4 回トグルで整合）.

    UNIQUE 制約が効いていれば like_count は 1,0,1,0 で振動する。
    壊れていれば 1,2,3,4 と単調増加するため、回帰が即発見できる。
    """
    fresh_client, _, _ = _register_and_login(client)
    post_id = fresh_client.post("/posts/", data={"title": "uniq"}).json()["id"]

    states = [fresh_client.post(f"/posts/{post_id}/like").json() for _ in range(4)]

    assert [s["liked"] for s in states] == [True, False, True, False]
    assert [s["like_count"] for s in states] == [1, 0, 1, 0]

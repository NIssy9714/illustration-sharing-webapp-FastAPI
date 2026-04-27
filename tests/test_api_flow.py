def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_login_create_like_delete_flow(client):
    # 登録（成功時にトークンを返しつつ Cookie もセット）
    r = client.post(
        "/auth/register",
        json={"username": "u1", "password": "password123!"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["username"] == "u1"
    assert "access_token" in body
    # Cookie に保存されていること
    assert client.cookies.get("access_token") is not None

    # ログイン（Cookie が更新される）
    r = client.post(
        "/auth/login",
        json={"username": "u1", "password": "password123!"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 投稿作成（Form data。Cookie 認証で OK）
    r = client.post(
        "/posts/",
        data={"title": "hello", "body": "body"},
    )
    assert r.status_code == 201, r.text
    post = r.json()
    post_id = post["id"]
    assert post["title"] == "hello"

    # 投稿一覧
    r = client.get("/posts/")
    assert r.status_code == 200
    assert any(p["id"] == post_id for p in r.json())

    # いいね ON（Bearer 互換も検証）
    r = client.post(f"/posts/{post_id}/like", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["liked"] is True
    assert data["like_count"] == 1

    # いいね OFF
    r = client.post(f"/posts/{post_id}/like", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["liked"] is False
    assert data["like_count"] == 0

    # 削除（Cookie 認証）
    r = client.delete(f"/posts/{post_id}")
    assert r.status_code == 204

    # 削除後 → 404
    r = client.get(f"/posts/{post_id}")
    assert r.status_code == 404

    # ログアウトで Cookie が消える
    r = client.post("/auth/logout")
    assert r.status_code == 200


def test_auth_required(client):
    # Cookie もヘッダもなしで投稿作成 → 401
    fresh = client.__class__(client.app)
    r = fresh.post("/posts/", data={"title": "x"})
    assert r.status_code == 401


def test_like_unique_constraint(client):
    """同一ユーザー × 同一投稿のいいねが重複登録されないこと."""
    fresh = client.__class__(client.app)
    fresh.post(
        "/auth/register",
        json={"username": "uniq_user", "password": "password123!"},
    )
    r = fresh.post("/posts/", data={"title": "p", "body": ""})
    assert r.status_code == 201
    post_id = r.json()["id"]

    # いいね ON → OFF → ON → OFF が正しく往復する（DB 整合）
    states = []
    for _ in range(4):
        r = fresh.post(f"/posts/{post_id}/like")
        assert r.status_code == 200
        states.append(r.json())
    assert [s["liked"] for s in states] == [True, False, True, False]
    assert [s["like_count"] for s in states] == [1, 0, 1, 0]

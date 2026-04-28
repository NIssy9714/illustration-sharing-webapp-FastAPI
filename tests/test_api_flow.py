def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_login_create_like_delete_flow(client):
    # 登録（成功時にトークンを返しつつ Cookie もセット）
    response = client.post(
        "/auth/register",
        json={"username": "u1", "password": "password123!"},
    )
    assert response.status_code == 201
    response_body = response.json()
    assert response_body["user"]["username"] == "u1"
    assert "access_token" in response_body
    # Cookie に保存されていること
    assert client.cookies.get("access_token") is not None

    # ログイン（Cookie が更新される）
    response = client.post(
        "/auth/login",
        json={"username": "u1", "password": "password123!"},
    )
    assert response.status_code == 200
    access_token = response.json()["access_token"]
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    # 投稿作成（Form data。Cookie 認証で OK）
    response = client.post(
        "/posts/",
        data={"title": "hello", "body": "body"},
    )
    assert response.status_code == 201, response.text
    created_post = response.json()
    post_id = created_post["id"]
    assert created_post["title"] == "hello"

    # 投稿一覧
    response = client.get("/posts/")
    assert response.status_code == 200
    assert any(post["id"] == post_id for post in response.json())

    # いいね ON（Bearer 互換も検証）
    response = client.post(f"/posts/{post_id}/like", headers=auth_headers)
    assert response.status_code == 200
    like_response = response.json()
    assert like_response["liked"] is True
    assert like_response["like_count"] == 1

    # いいね OFF
    response = client.post(f"/posts/{post_id}/like", headers=auth_headers)
    assert response.status_code == 200
    like_response = response.json()
    assert like_response["liked"] is False
    assert like_response["like_count"] == 0

    # 削除（Cookie 認証）
    response = client.delete(f"/posts/{post_id}")
    assert response.status_code == 204

    # 削除後 → 404
    response = client.get(f"/posts/{post_id}")
    assert response.status_code == 404

    # ログアウトで Cookie が消える
    response = client.post("/auth/logout")
    assert response.status_code == 200


def test_auth_required(client):
    # Cookie もヘッダもなしで投稿作成 → 401
    unauthenticated_client = client.__class__(client.app)
    response = unauthenticated_client.post("/posts/", data={"title": "x"})
    assert response.status_code == 401


def test_like_unique_constraint(client):
    """同一ユーザー × 同一投稿のいいねが重複登録されないこと."""
    unauthenticated_client = client.__class__(client.app)
    unauthenticated_client.post(
        "/auth/register",
        json={"username": "uniq_user", "password": "password123!"},
    )
    response = unauthenticated_client.post("/posts/", data={"title": "p", "body": ""})
    assert response.status_code == 201
    post_id = response.json()["id"]

    # いいね ON → OFF → ON → OFF が正しく往復する（DB 整合）
    like_states = []
    for _ in range(4):
        response = unauthenticated_client.post(f"/posts/{post_id}/like")
        assert response.status_code == 200
        like_states.append(response.json())
    assert [state["liked"] for state in like_states] == [True, False, True, False]
    assert [state["like_count"] for state in like_states] == [1, 0, 1, 0]

"""JWT 認証の境界テスト。

正常系は test_api_flow.py が担当。
ここでは「攻撃者目線で投げ込まれうる不正トークン」を網羅する:
  - 期限切れトークン
  - 署名改ざんトークン
  - 形式不正トークン（"abc.def.ghi" ですらない）
  - 存在しないユーザー ID を sub に持つ正規署名トークン
  - sub クレーム欠落
  - sub が数値変換不能な文字列

検証エンドポイントは保護リソースの代表として GET /posts/{id} ではなく、
「認証必須かつ副作用が小さい」DELETE /posts/{id}（404 / 401 の差）と
POST /posts/{id}/like を使う。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import get_settings
from app.routers.auth import ALGORITHM


def _make_token(
    sub: str | None,
    expires_in: timedelta = timedelta(minutes=30),
    secret: str | None = None,
) -> str:
    """テスト用 JWT 生成ヘルパー。

    expires_in に負の値を渡せば期限切れトークンを作れる。
    secret を別値にすれば署名改ざん相当のトークンを作れる。
    """
    settings = get_settings()
    payload: dict = {"exp": datetime.now(timezone.utc) + expires_in}
    if sub is not None:
        payload["sub"] = sub
    return jwt.encode(payload, secret or settings.secret_key, algorithm=ALGORITHM)


# ------------------------------------------------------------
# 不正トークンを Authorization ヘッダで送る → 401
# ------------------------------------------------------------


def test_expired_token_rejected(client) -> None:
    """exp が過去のトークンは ExpiredSignatureError → 401."""
    expired_token = _make_token(sub="1", expires_in=timedelta(minutes=-1))
    fresh_client = client.__class__(client.app)  # Cookie 持ち越し防止

    response = fresh_client.post(
        "/posts/",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401
    assert "有効期限" in response.json()["detail"]


def test_tampered_signature_rejected(client) -> None:
    """別の秘密鍵で署名したトークンは PyJWTError → 401."""
    tampered_token = _make_token(sub="1", secret="attacker-knows-not-the-real-key")
    fresh_client = client.__class__(client.app)

    response = fresh_client.post(
        "/posts/",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {tampered_token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "トークンが無効です"


@pytest.mark.parametrize(
    "garbage_token",
    [
        "not-a-jwt-at-all",  # ドット区切りすらない
        "aaa.bbb.ccc",  # 形式は JWT 風だが base64 もデコード不能
        "",  # 空文字（Bearer の後ろ空）
    ],
)
def test_malformed_token_rejected(client, garbage_token: str) -> None:
    """JWT 形式から逸脱したトークンは全て 401 で弾く."""
    fresh_client = client.__class__(client.app)
    response = fresh_client.post(
        "/posts/",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {garbage_token}"},
    )
    assert response.status_code == 401


def test_missing_sub_claim_rejected(client) -> None:
    """sub クレームを欠いた正規署名トークンは 401."""
    token = _make_token(sub=None)
    fresh_client = client.__class__(client.app)

    response = fresh_client.post(
        "/posts/",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "無効なトークンです"


def test_non_numeric_sub_rejected(client) -> None:
    """sub が int に変換できない文字列なら 401."""
    token = _make_token(sub="not-an-integer")
    fresh_client = client.__class__(client.app)

    response = fresh_client.post(
        "/posts/",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_token_for_nonexistent_user_rejected(client) -> None:
    """署名・形式・期限はすべて正しいが、sub のユーザーが DB に存在しない場合 401.

    削除済みユーザーのトークンが残っているシナリオの防御。
    """
    token = _make_token(sub="999999")  # 確実に存在しない ID
    fresh_client = client.__class__(client.app)

    response = fresh_client.post(
        "/posts/",
        data={"title": "x"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "ユーザーが見つかりません"

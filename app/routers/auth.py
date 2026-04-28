"""認証ルーター。

ユーザー登録、ログイン、ログアウトのエンドポイントを提供する。
JWT を HttpOnly Cookie に保存する方式を主とし、Authorization: Bearer も互換維持で受け付ける。
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.limiter import limiter
from app.db import User, get_db
from app.schemas import UserLogin, UserRegister, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

settings = get_settings()
ALGORITHM = "HS256"
COOKIE_NAME = "access_token"


# ==============================================================================
# パスワード/トークン ユーティリティ
# ==============================================================================


def _to_bcrypt_bytes(password: str) -> bytes:
    # bcrypt は 72 バイト超を受け付けないため上限に合わせる
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    """パスワードをハッシュ化."""
    hashed = bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """パスワードを検証."""
    try:
        return bcrypt.checkpw(
            _to_bcrypt_bytes(plain_password),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # 旧 Flask 版 (pbkdf2) ハッシュ等、認識できないハッシュは認証失敗扱い
        return False


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """アクセストークンを作成."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.access_token_expire_minutes,
        )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def _set_auth_cookie(response: Response, token: str) -> None:
    """HttpOnly Cookie にトークンを格納."""
    max_age = settings.access_token_expire_minutes * 60
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


# ==============================================================================
# 認証 Dependency
# ==============================================================================


http_bearer = HTTPBearer(auto_error=False)


def _decode_token(token: str) -> int:
    """トークンを検証して user_id を返す."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as expired_error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンの有効期限が切れています",
            headers={"WWW-Authenticate": "Bearer"},
        ) from expired_error
    except jwt.PyJWTError as jwt_error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="トークンが無効です",
            headers={"WWW-Authenticate": "Bearer"},
        ) from jwt_error

    # "sub" は JWT 標準のクレーム名。ここではユーザー ID を文字列で格納している
    subject_user_id = payload.get("sub")
    if subject_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンです",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return int(subject_user_id)
    except (TypeError, ValueError) as conversion_error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無効なトークンです",
            headers={"WWW-Authenticate": "Bearer"},
        ) from conversion_error


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    """Cookie 優先、なければ Authorization: Bearer ヘッダから取得."""
    cookie_token = request.cookies.get(COOKIE_NAME)
    if cookie_token:
        return cookie_token
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """認証必須のエンドポイント用 Dependency."""
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証トークンがありません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = _decode_token(token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザーが見つかりません",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User | None:
    """テンプレート用：未ログインなら None を返す."""
    token = _extract_token(request, credentials)
    if not token:
        return None
    try:
        user_id = _decode_token(token)
    except HTTPException:
        return None
    return db.query(User).filter(User.id == user_id).first()


# ==============================================================================
# エンドポイント
# ==============================================================================


def _issue_token_for(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def register(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    """新規ユーザー登録。登録成功時はそのままログイン状態にする."""
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="このユーザー名は既に登録されています",
        )

    new_user = User(
        username=user_data.username,
        password=hash_password(user_data.password),
    )
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError as integrity_error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ユーザー登録に失敗しました",
        ) from integrity_error

    token = _issue_token_for(new_user)
    _set_auth_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(new_user),
    }


@router.post("/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    user_data: UserLogin,
    db: Session = Depends(get_db),
):
    """ログイン処理。成功時にアクセストークンを Cookie に格納."""
    user = db.query(User).filter(User.username == user_data.username).first()
    if not user or not verify_password(user_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ユーザー名またはパスワードが間違っています",
        )

    token = _issue_token_for(user)
    _set_auth_cookie(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user),
    }


@router.post("/logout")
def logout(response: Response):
    """ログアウト処理。Cookie を削除する."""
    _clear_auth_cookie(response)
    return {"message": "ログアウトしました"}

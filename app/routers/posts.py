"""投稿ルーター。

投稿の作成、一覧取得、詳細表示、いいね、削除などのエンドポイントを提供する。
"""

import os

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.db import Like, Post, User, get_db
from app.image_service import process_uploaded_image
from app.routers.auth import get_current_user
from app.schemas import LikeResponse, PostResponse, PostWithLikes

router = APIRouter(prefix="/posts", tags=["posts"])


# ==============================================================================
# エンドポイント
# ==============================================================================


@router.get("/", response_model=list[PostResponse])
def get_posts(db: Session = Depends(get_db), limit: int = 100, offset: int = 0):
    """投稿一覧を取得。最新順."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return db.query(Post).order_by(desc(Post.created_at)).offset(offset).limit(limit).all()


@router.get("/{post_id}", response_model=PostWithLikes)
def get_post(post_id: int, db: Session = Depends(get_db)):
    """投稿詳細を取得."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="投稿が見つかりません",
        )

    like_count = db.query(Like).filter(Like.post_id == post_id).count()
    return PostWithLikes(
        id=post.id,
        user_id=post.user_id,
        title=post.title,
        filename=post.filename,
        body=post.body,
        created_at=post.created_at,
        like_count=like_count,
    )


@router.post("/", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/minute")
async def create_post(
    request: Request,
    title: str = Form(..., min_length=1, max_length=255),
    body: str = Form("", max_length=140),
    image: UploadFile = File(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新しい投稿（画像付き）を作成."""
    title = title.strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="タイトルが入力されていません",
        )

    filename = None
    # UploadFile は filename が空文字でも生成されるため、内容で判定
    if image and image.filename:
        filename, error = process_uploaded_image(
            image,
            upload_base_dir=os.path.join("static", "uploads"),
        )
        if error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error,
            )

    new_post = Post(
        user_id=current_user.id,
        title=title,
        filename=filename,
        body=body or None,
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)
    return new_post


@router.post("/{post_id}/like", response_model=LikeResponse)
@limiter.limit("60/minute")
def like_post(
    request: Request,
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """投稿に対していいねを付与／解除する."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="投稿が見つかりません",
        )

    existing_like = (
        db.query(Like).filter(Like.user_id == current_user.id, Like.post_id == post_id).first()
    )

    if existing_like:
        db.delete(existing_like)
        liked = False
    else:
        new_like = Like(user_id=current_user.id, post_id=post_id)
        db.add(new_like)
        liked = True

    try:
        db.commit()
    except IntegrityError:
        # UNIQUE(user_id, post_id) 違反 = 同時連打で重複登録試行 → 既にいいね済とみなす
        db.rollback()
        liked = True

    like_count = db.query(Like).filter(Like.post_id == post_id).count()
    return LikeResponse(liked=liked, like_count=like_count)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """投稿を削除."""
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="投稿が見つかりません",
        )

    is_owner = post.user_id == current_user.id
    if not (is_owner or current_user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="この投稿を削除する権限がありません",
        )

    if post.filename:
        uploads_root = os.path.realpath(os.path.join("static", "uploads"))
        target_paths = (
            os.path.join("static", "uploads", post.filename),
            os.path.join("static", "uploads", "thumbs", post.filename),
        )
        for target_path in target_paths:
            absolute_path = os.path.realpath(target_path)
            # uploads 配下以外には絶対に触れない（パストラバーサル防御）
            if not absolute_path.startswith(uploads_root):
                continue
            if os.path.exists(absolute_path):
                try:
                    os.remove(absolute_path)
                except OSError:
                    pass

    # 関連いいねを削除（CASCADE 未設定のため明示）
    db.query(Like).filter(Like.post_id == post_id).delete()
    db.delete(post)
    db.commit()

"""検索ルーター。投稿の検索機能を提供."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import Post, get_db
from app.schemas import SearchResults

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResults)
def search_posts(
    query: str = Query("", max_length=100),
    db: Session = Depends(get_db),
):
    """タイトルに部分一致する投稿を検索."""
    keyword = query.strip()
    posts = (
        db.query(Post)
        .filter(Post.title.ilike(f"%{keyword}%"))
        .order_by(desc(Post.created_at))
        .all()
    )
    return SearchResults(search_keyword=keyword, posts=posts)

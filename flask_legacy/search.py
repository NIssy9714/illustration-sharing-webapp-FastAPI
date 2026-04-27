"""検索機能を提供するモジュール。

タイトルに検索キーワードを含む投稿を検索し、検索結果を表示します。
"""

from db import get_db
from flask import abort, render_template, request


def search():
    """タイトルに部分一致する投稿を検索して結果ページを表示する。"""
    search_keyword = request.args.get("search_query", "").strip()

    try:
        database = get_db()
        rows = database.execute(
            """
            SELECT id, user_id, title, filename, body, created_at
            FROM posts
            WHERE title LIKE ?
            ORDER BY created_at DESC
            """,
            (f"%{search_keyword}%",),
        ).fetchall()
        posts = [dict(row) for row in rows]
        return render_template(
            "search_results.html",
            posts=posts,
            search_keyword=search_keyword,
            title="検索結果",
        )
    except Exception:
        abort(500)

"""投稿表示・投稿操作に関する処理をまとめたモジュール。

このモジュールでは、投稿の作成、一覧取得、投稿詳細の表示、
いいねの切り替え、投稿削除などの処理を定義しています。

ルート登録自体は `app.py` で行い、ここでは実際のビジネスロジックを担当します。
"""

import os

from db import get_db
from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from image_service import process_uploaded_image


def upload():
    """新しい投稿（画像付き）を作成する処理。

    POST リクエスト時にフォーム入力を検証し、画像ファイルを保存してから
    posts テーブルにレコードを追加します。
    """
    if request.method == "POST":
        if not current_user.is_authenticated:
            abort(401)
        title = request.form["title"]
        body = request.form.get("body", "")
        image = request.files.get("image")

        if not title or title.strip() == "":
            flash("タイトルが入力されていません")
            return render_template("upload.html", title="投稿")

        filename, error = process_uploaded_image(
            image,
            upload_base_dir=os.path.join("static", "uploads"),
        )
        if error:
            flash(error)
            return render_template("upload.html", title="投稿")

        try:
            database = get_db()
            database.execute(
                "INSERT INTO posts (user_id, title, filename, body) VALUES (?, ?, ?, ?)",
                (int(current_user.id), title, filename, body),
            )
            database.commit()
        except Exception:
            flash("投稿の保存に失敗しました")
            return render_template("upload.html", title="投稿")

        return redirect("/")

    return render_template("upload.html", title="投稿")


def home():
    """トップページで投稿一覧を表示する。

    投稿は作成日時が新しい順（降順）で表示されます。
    """
    try:
        database = get_db()
        rows = database.execute(
            "SELECT id, user_id, title, filename, body, created_at FROM posts ORDER BY created_at DESC",
        ).fetchall()
        posts = [dict(row) for row in rows]
        return render_template("index.html", posts=posts, title="投稿一覧")
    except Exception:
        abort(500)


def post(id):
    """指定 ID の投稿詳細を表示する。"""
    try:
        database = get_db()
        row = database.execute(
            "SELECT id, user_id, title, filename, body, created_at FROM posts WHERE id=?",
            (id,),
        ).fetchone()
        if not row:
            abort(404)
        post_data = dict(row)
        like_count = database.execute(
            "SELECT COUNT(*) FROM likes WHERE post_id=?",
            (id,),
        ).fetchone()[0]
        return render_template(
            "post.html",
            post=post_data,
            like_count=like_count,
        )
    except Exception:
        abort(500)


@login_required
def like(id):
    """投稿に対して「いいね」を付与／解除する。"""
    if not current_user.is_authenticated:
        abort(401)
    try:
        database = get_db()
        existing = database.execute(
            "SELECT id FROM likes WHERE user_id=? AND post_id=?",
            (int(current_user.id), id),
        ).fetchone()

        if existing:
            database.execute(
                "DELETE FROM likes WHERE user_id=? AND post_id=?",
                (int(current_user.id), id),
            )
        else:
            database.execute(
                "INSERT INTO likes (user_id, post_id) VALUES (?, ?)",
                (int(current_user.id), id),
            )
        database.commit()
        return redirect(url_for("post", id=id))
    except Exception:
        abort(500)


@login_required
def delete(id):
    """投稿を削除する。

    投稿の所有者または管理者ユーザー（username == "admin"）のみが削除可能。
    削除時は DB レコードだけでなく、画像ファイルとサムネイルも削除します。
    """
    if not current_user.is_authenticated:
        abort(401)
    try:
        database = get_db()
        row = database.execute(
            "SELECT user_id, filename FROM posts WHERE id=?",
            (id,),
        ).fetchone()
        if not row:
            return redirect(url_for("home"))

        owner_id = row["user_id"]
        filename = row["filename"]

        if int(current_user.id) != int(owner_id) and current_user.username != "admin":
            abort(403)

        for path in (
            os.path.join("static", "uploads", filename),
            os.path.join("static", "uploads", "thumbs", filename),
        ):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

        database.execute("DELETE FROM posts WHERE id=?", (id,))
        database.commit()
        return redirect(url_for("home"))
    except Exception:
        abort(500)

"""認証機能（ユーザー登録・ログイン・ログアウト）を提供するモジュール。

このモジュールは Flask-Login の仕組みを使い、
セッションからユーザーを復元したり、ログイン／ログアウトの処理を提供します。

ルート定義自体は `app.py` 側で行っていますが、
処理ロジックと認証モデルはここに集約しています。
"""

import re

from db import get_db
from flask import flash, redirect, render_template, request
from flask_login import (
    LoginManager,
    UserMixin,
    login_required,
    login_user,
    logout_user,
)
from werkzeug.security import check_password_hash, generate_password_hash

# Flask-Login の設定
login_manager = LoginManager()
login_manager.login_view = "login"  # 未ログイン時にリダイレクトするエンドポイント名


class User(UserMixin):
    """Flask-Login が扱うユーザーオブジェクト。

    アプリ内では、ユーザーの ID、ユーザー名、パスワードハッシュを保持します。
    """

    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash


@login_manager.user_loader
def load_user(user_id):
    """セッションに格納されている user_id から User オブジェクトを復元する。"""
    try:
        database = get_db()
        row = database.execute(
            "SELECT id, username, password FROM users WHERE id=?",
            (user_id,),
        ).fetchone()
        if row:
            return User(row["id"], row["username"], row["password"])
    except Exception:
        # Flask の current_app.logger へアクセスすると循環インポートになるため、
        # ここでは例外内容を記録していません。
        pass
    return None


def register():
    """新規ユーザー登録を処理する。

    フォーム入力のバリデーションを行い、問題がなければパスワードをハッシュ化して
    users テーブルに保存します。
    """
    if request.method == "POST":
        username = request.form["username"]
        raw_password = request.form["password"]

        if not raw_password:
            flash("パスワードを入力してください。")
            return render_template("register.html", title="新規登録")
        if len(raw_password) < 8:
            flash("パスワードは8文字以上にしてください。")
            return render_template("register.html", title="新規登録")
        if len(raw_password) > 128:
            flash("パスワードは128文字以下にしてください。")
            return render_template("register.html", title="新規登録")
        if not re.match(r"^[\x21-\x7E]+$", raw_password):
            flash(
                "パスワードは英数字および記号（半角）で入力してください。日本語や全角文字は使えません。",
            )
            return render_template("register.html", title="新規登録")

        password_hash = generate_password_hash(raw_password)
        try:
            database = get_db()
            database.execute(
                "INSERT INTO users (username, password) VALUES (?, ?)",
                (username, password_hash),
            )
            database.commit()
        except Exception:
            flash("登録に失敗しました。")
            return render_template("register.html", title="新規登録")

        return redirect("/login")

    return render_template("register.html", title="新規登録")


def login():
    """ログイン処理を行う。"""
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        try:
            database = get_db()
            row = database.execute(
                "SELECT id, username, password FROM users WHERE username=?",
                (username,),
            ).fetchone()
            if row and check_password_hash(row["password"], password):
                login_user(User(row["id"], row["username"], row["password"]))
                return redirect("/")
        except Exception:
            pass
        return "ログイン失敗"

    return render_template("login.html", title="ログイン")


@login_required
def logout():
    """ログアウトしてトップページへリダイレクトする。"""
    logout_user()
    return redirect("/")

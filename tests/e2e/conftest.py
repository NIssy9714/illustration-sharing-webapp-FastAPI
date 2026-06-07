"""E2E テスト用の共通 fixture（部品）を定義するファイル。

このファイルの役割:
- uvicorn（FastAPI を動かすサーバ）を別プロセスで起動する
- /health エンドポイントが応答するまで待ち、ブラウザから叩く URL を配る
- テスト間でユーザー名がぶつからないよう、毎回ユニークな名前を生成する
- テスト用のダミー画像（PNG バイナリ）を作る
- 失敗時のスクリーンショット・動画・トレースは tests/e2e/artifacts に保存する

pytest が自動で読み込み、各テスト関数が引数名で fixture を受け取れる。
"""

from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest
from PIL import Image

# このファイル（tests/e2e/conftest.py）から 2 階層上 = プロジェクトルート
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# テスト失敗時の証拠（スクリーンショット等）を置くディレクトリ
ARTIFACTS_DIR = PROJECT_ROOT / "tests" / "e2e" / "artifacts"


def _pick_free_port() -> int:
    """OS から空いているポート番号を 1 つ取得する。

    開発機ですでに 8000 番が使われていてもテストが落ちないように、
    毎回 OS にポートを割り当てさせる方式を採る。
    取得直後にソケットを閉じるため、別プロセスが横取りする可能性は
    ゼロではないが、ローカルテスト用途なら実用上問題ない。
    """
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(("127.0.0.1", 0))  # 0 を指定すると OS が空きポートを割り当てる
    assigned_port = server_socket.getsockname()[1]
    server_socket.close()
    return assigned_port


def _wait_until_healthy(base_url: str, timeout: float = 30.0) -> None:
    """指定 URL の /health に GET し、200 が返るまで最大 timeout 秒待つ。

    uvicorn の起動には数秒かかるため、すぐにテストを始めると接続失敗する。
    最後に失敗した例外も保存しておき、タイムアウト時にメッセージへ含める。
    """
    deadline = time.time() + timeout
    last_exception: Exception | None = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/health", timeout=1.0)
            if response.status_code == 200:
                return
        except Exception as exception:
            last_exception = exception
        time.sleep(0.3)  # 0.3 秒待ってから再試行
    raise RuntimeError(f"E2E サーバが {timeout}s 以内に起動しませんでした: {last_exception!r}")


@pytest.fixture(scope="session")
def e2e_server_url() -> str:
    """テスト全体で 1 度だけ uvicorn を起動し、ベース URL を返す。

    scope="session" にすることで、テスト関数ごとにサーバを起動し直さず
    高速化している。テスト終了時にサーバプロセスと一時 DB ファイルを片付ける。
    """
    # 空きポートを取得して http://127.0.0.1:XXXX 形式の URL を組み立てる
    port = _pick_free_port()
    base_url = f"http://127.0.0.1:{port}"

    # テスト用 SQLite を一時ファイルとして作成
    # （本番 DB やローカル開発用 database.db を汚さないため）
    database_file = tempfile.NamedTemporaryFile(suffix="_e2e.db", delete=False)
    database_file.close()
    database_path = database_file.name

    # uvicorn に渡す環境変数を組み立てる
    # os.environ.copy() で現在の環境を引き継ぎつつ、必要な値だけ上書きする
    environment_variables = os.environ.copy()
    environment_variables.update(
        {
            "SECRET_KEY": "e2e-secret-key",
            # SQLite のファイル URL は「sqlite:///」(スラッシュ 3 つ) + 絶対パス
            "DATABASE_URL": f"sqlite:///{database_path}",
            # APP_ENV を "test" にすると Alembic がスキップされるため、
            # 通常起動と同じ "dev" にしてテーブル自動作成を行わせる
            "APP_ENV": "dev",
            "ALLOWED_ORIGINS": base_url,
            # E2E は同一 IP から短時間に多数の登録/ログインを行うため、
            # レート制限（register 5/min 等）を無効化して 429 による誤検知を防ぐ
            "RATELIMIT_ENABLED": "false",
            # E2E は HTTP（HTTPS ではない）で動かすので Cookie の Secure 属性を外す
            "COOKIE_SECURE": "false",
            "COOKIE_SAMESITE": "lax",
        }
    )

    # 別プロセスで uvicorn を起動する
    # subprocess.Popen は「ノンブロッキング」で起動し、すぐに次の行へ進む
    server_process = subprocess.Popen(
        [
            sys.executable,  # 現在動いている Python と同じインタプリタを使う
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(PROJECT_ROOT),  # uvicorn の作業ディレクトリをプロジェクトルートに
        env=environment_variables,
        stdout=subprocess.DEVNULL,  # 標準出力を捨てる（テストログを汚さない）
        stderr=subprocess.DEVNULL,  # 標準エラーも同様
    )

    try:
        # サーバが応答するようになるまで待ってから、テストへ URL を渡す
        _wait_until_healthy(base_url)
        yield base_url
    finally:
        # ---- ここからテスト終了後のクリーンアップ ----
        # process.poll() が None なら「まだ生きている」状態
        if server_process.poll() is None:
            server_process.terminate()  # まずは穏やかに停止リクエスト
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 5 秒待っても止まらなければ強制終了
                server_process.kill()
                server_process.wait(timeout=5)
        # 一時 DB ファイルを削除（既に消えていてもエラーにしない）
        try:
            os.remove(database_path)
        except OSError:
            pass


# ------------------------------------------------------------
# pytest-playwright（ブラウザ自動操作）の挙動カスタマイズ
# ------------------------------------------------------------


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, e2e_server_url):
    """全テストで共通のブラウザ設定（base_url など）を渡す。

    base_url を指定しておくと、テスト中 page.goto("/login") のような
    相対 URL が使える。スクリーンショット等の保存設定は
    pytest-playwright のコマンドラインオプション
    （例: --screenshot=only-on-failure）に任せる方針。
    """
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return {
        **browser_context_args,
        "base_url": e2e_server_url,
        "ignore_https_errors": True,
    }


# ------------------------------------------------------------
# テストデータ生成 fixture（毎テスト呼ばれる）
# ------------------------------------------------------------


@pytest.fixture
def unique_username() -> str:
    """テストごとに重複しないユーザー名を返す。

    DB に user テーブルがあり username UNIQUE 制約があるため、
    同じ名前で 2 回登録するとテストが落ちる。これを防ぐ目的。
    """
    return f"e2e_{uuid.uuid4().hex[:10]}"


@pytest.fixture
def valid_password() -> str:
    """登録バリデーション（英大文字+小文字+数字+記号、8文字以上）を満たすパスワード。"""
    return "TestPass1!"


@pytest.fixture
def tiny_png_bytes() -> bytes:
    """200x200 ピクセルの真っ赤な PNG 画像をバイナリ（バイト列）で返す。

    実ファイルを保存せずにアップロードテストを行うため、
    Pillow（PIL）でメモリ上に PNG を作って返す。
    """
    image = Image.new("RGB", (200, 200), color=(255, 0, 0))  # 赤色 RGB(255,0,0)
    buffer = io.BytesIO()  # メモリ上の仮想ファイル
    image.save(buffer, format="PNG")  # 仮想ファイルへ PNG として書き出し
    return buffer.getvalue()  # バイト列として取り出し


@pytest.fixture
def register_user(page, e2e_server_url, valid_password):
    """新規ユーザー登録 → ログイン状態にした page を返すヘルパー fixture。

    テスト本体で `register_user(unique_username)` と呼ぶだけで、
    /register フォームの入力 → 送信 → トップページ遷移までを行う。
    """

    def _register(username: str) -> None:
        # 登録ページを開く
        page.goto(f"{e2e_server_url}/register")
        # フォームの input にユーザー名・パスワードを入力
        page.fill('input[name="username"]', username)
        page.fill('input[name="password"]', valid_password)
        # 送信ボタンを押すと JavaScript が fetch で API を叩き、
        # 成功時に location.href = '/' でトップへ遷移する。
        # その遷移完了を expect_navigation で待つ。
        with page.expect_navigation(url=f"{e2e_server_url}/"):
            page.click('#register-form button[type="submit"]')

    return _register

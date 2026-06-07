"""認証フロー（新規登録・ログイン・ログアウト）の E2E テスト。

テスト対象:
- 新規登録 → 自動的にログイン状態になり、ログアウトできること
- 既存ユーザーが正しい資格情報でログインできること
- 間違ったパスワードを入れたらエラーメッセージが画面に出ること
- 未ログインで /upload を開くと、フォームではなくログイン誘導が出ること

E2E（End-to-End）= 実ブラウザで実サーバを操作し、ユーザー視点で動作確認する形式。
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_register_then_logout(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    valid_password: str,
) -> None:
    """新規登録 → 自動ログイン → ログアウト の一連を検証。"""
    # 1. /register ページを開く
    page.goto(f"{e2e_server_url}/register")

    # 2. フォームを埋めて送信ボタンを押す（送信成功でトップへ遷移する仕様）
    page.fill('input[name="username"]', unique_username)
    page.fill('input[name="password"]', valid_password)
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click('#register-form button[type="submit"]')

    # 3. ナビゲーション領域に自分のユーザー名が出ていればログイン成功
    expect(page.locator(".nav-username")).to_contain_text(unique_username)

    # 4. ログアウトボタンを押す → トップへ戻り、未ログイン用のリンクが復活する
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click("#logout-btn")
    expect(page.get_by_role("link", name="ログイン")).to_be_visible()
    expect(page.get_by_role("link", name="新規登録")).to_be_visible()


def test_login_with_existing_user(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    valid_password: str,
    register_user,
) -> None:
    """事前登録済みのユーザーが /login から再ログインできるか検証。"""
    # 1. fixture で先に登録（登録直後はログイン状態になる）
    register_user(unique_username)
    # 2. いったんログアウトして未ログイン状態にする
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click("#logout-btn")

    # 3. /login で同じユーザー名・パスワードを入れて送信
    page.goto(f"{e2e_server_url}/login")
    page.fill('input[name="username"]', unique_username)
    page.fill('input[name="password"]', valid_password)
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click('#login-form button[type="submit"]')

    # 4. ナビゲーションに自分のユーザー名が表示されていれば成功
    expect(page.locator(".nav-username")).to_contain_text(unique_username)


def test_login_failure_shows_error_message(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
) -> None:
    """登録していないユーザー名でログインを試み、エラー表示と URL を確認。"""
    page.goto(f"{e2e_server_url}/login")
    page.fill('input[name="username"]', unique_username)
    page.fill('input[name="password"]', "WrongPass1!")
    page.click('#login-form button[type="submit"]')

    # ページ遷移はせず、#error-msg にエラーが表示されるはず
    error_message_element = page.locator("#error-msg")
    expect(error_message_element).to_be_visible()
    # メッセージに「ユーザー名」または「パスワード」が含まれていれば良しとする
    expect(error_message_element).to_contain_text(re.compile(r"ユーザー名|パスワード"))
    # URL は /login のままであることも確認
    expect(page).to_have_url(re.compile(r"/login$"))


def test_upload_page_guides_unauthenticated_users(page: Page, e2e_server_url: str) -> None:
    """未ログインで /upload を開いたら、フォームではなくログイン誘導が出る仕様を確認。"""
    page.goto(f"{e2e_server_url}/upload")
    # 案内文（段落）内に「ログイン」リンクが表示されていること
    # ※ヘッダーのナビにも同名リンクがあるため、段落にスコープして一意に特定する
    expect(page.get_by_role("paragraph").get_by_role("link", name="ログイン")).to_be_visible()
    # 投稿フォーム（id="upload-form"）は描画されていないはず（要素数 0）
    expect(page.locator("#upload-form")).to_have_count(0)

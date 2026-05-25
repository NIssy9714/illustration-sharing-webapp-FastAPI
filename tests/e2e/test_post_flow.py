"""投稿の作成 → 一覧 → 詳細 → いいね → 削除、までを通しで検証する E2E テスト。

特に確かめたい挙動:
- 実画像ファイル（PNG バイナリ）を multipart/form-data で送信し、
  サーバ側 Pillow による検証を通過すること
- いいねボタン押下でカウントがページリロード無し（JavaScript）で更新されること
- ブラウザの confirm() ダイアログを許可した削除フローで、一覧から消えること
- 未ログイン状態で /posts/{id}/like を叩くと、/login にリダイレクトされること
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _create_post(
    page: Page,
    e2e_server_url: str,
    title: str,
    body: str,
    image_bytes: bytes | None = None,
) -> None:
    """/upload フォームを使って投稿を 1 件作成するヘルパー関数。

    image_bytes に None を渡すと画像なし投稿になる。
    送信後はトップページへ遷移する仕様のため、その遷移完了まで待つ。
    """
    page.goto(f"{e2e_server_url}/upload")
    page.fill('input[name="title"]', title)
    page.fill('textarea[name="body"]', body)
    if image_bytes is not None:
        # set_input_files でメモリ上のバイナリを「ファイル選択」相当として渡す
        page.set_input_files(
            'input[name="image"]',
            files=[
                {
                    "name": "test.png",
                    "mimeType": "image/png",
                    "buffer": image_bytes,
                }
            ],
        )
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click('button[type="submit"]')


def test_create_post_with_image_and_view_detail(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    register_user,
    tiny_png_bytes: bytes,
) -> None:
    """画像付き投稿を作成し、一覧と詳細ページに正しく出るか確認。"""
    # 1. ユーザー登録（自動でログイン）
    register_user(unique_username)

    # 2. 画像付きで投稿を作成
    title = f"E2E画像投稿_{unique_username}"
    _create_post(page, e2e_server_url, title, "本文サンプル", tiny_png_bytes)

    # 3. トップ一覧に投稿タイトルがリンクとして現れる
    expect(page.get_by_role("link", name=title)).to_be_visible()

    # 4. 詳細ページへ遷移して内容を確認
    page.get_by_role("link", name=title).first.click()
    expect(page).to_have_url(re.compile(r"/post/\d+$"))  # /post/123 形式
    expect(page.locator("h2")).to_contain_text(title)
    # <figure> 内に <img> が 1 つだけ描画されている（サムネイルではなく本体画像）
    expect(page.locator("figure img")).to_have_count(1)


def test_like_button_toggles_count_without_reload(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    register_user,
) -> None:
    """いいねボタンの 0→1→0 トグルがページリロードなしで反映されるか確認。"""
    register_user(unique_username)
    title = f"E2Eいいね_{unique_username}"
    _create_post(page, e2e_server_url, title, "")

    # 一覧から詳細ページへ
    page.get_by_role("link", name=title).first.click()

    # 初期表示は「0 いいね」
    like_count_element = page.locator("#like-count")
    expect(like_count_element).to_contain_text("0 いいね")

    # 1 回押す → 1
    page.click("#like-btn")
    expect(like_count_element).to_contain_text("1 いいね")

    # もう 1 回押す → 0（トグル＝もう一度押すと取り消す動作）
    page.click("#like-btn")
    expect(like_count_element).to_contain_text("0 いいね")


def test_delete_post_removes_it_from_listing(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    register_user,
) -> None:
    """投稿者本人が削除すると、一覧からその投稿が消えるか確認。"""
    register_user(unique_username)
    title = f"E2E削除_{unique_username}"
    _create_post(page, e2e_server_url, title, "")

    # 詳細ページへ移動 → 削除ボタンを押す
    # 削除前にブラウザ標準の confirm() ダイアログが出るので、
    # そのダイアログに対して accept（OK）を返すリスナーを 1 回だけ仕込む
    page.get_by_role("link", name=title).first.click()
    page.once("dialog", lambda dialog: dialog.accept())

    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click("#delete-btn")

    # 一覧から該当タイトルのリンクが消えていることを確認（要素数 0）
    expect(page.get_by_role("link", name=title)).to_have_count(0)


def test_unauthenticated_like_redirects_to_login(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    register_user,
    tiny_png_bytes: bytes,
) -> None:
    """未ログインでいいねを押した場合、/login へリダイレクトされるか確認。"""
    # 1. 投稿者ユーザー A で投稿を作成
    register_user(unique_username)
    title = f"E2E他者投稿_{unique_username}"
    _create_post(page, e2e_server_url, title, "", tiny_png_bytes)
    post_link_element = page.get_by_role("link", name=title).first
    expect(post_link_element).to_be_visible()

    # 2. ログアウトして未ログイン状態にする
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click("#logout-btn")

    # 3. 未ログインで詳細ページへ → いいね押下 → /login にリダイレクトされる
    page.get_by_role("link", name=title).first.click()
    with page.expect_navigation(url=re.compile(r"/login$")):
        page.click("#like-btn")

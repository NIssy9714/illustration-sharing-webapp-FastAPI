"""検索画面の E2E テスト。

確認項目:
- ヘッダーの検索フォームに語句を入れて送信すると /search?... に遷移する
- ヒットありの場合は結果ページに該当タイトルのリンクが表示される
- ヒット無しの場合は「該当する投稿が見つかりませんでした」メッセージが出る
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_search_finds_matching_title(
    page: Page,
    e2e_server_url: str,
    unique_username: str,
    register_user,
) -> None:
    """ユニークなタイトルで投稿し、それが検索でヒットすることを確認。"""
    # 1. ユーザー登録（自動ログイン）して投稿を 1 件作る
    register_user(unique_username)
    title = f"検索対象_{unique_username}"
    page.goto(f"{e2e_server_url}/upload")
    page.fill('input[name="title"]', title)
    page.fill('textarea[name="body"]', "")
    with page.expect_navigation(url=f"{e2e_server_url}/"):
        page.click('button[type="submit"]')

    # 2. ヘッダーの検索フォームにキーワードを入れて検索ボタンを押す
    # username はユニークなので、ヒット 1 件のみが期待される
    search_keyword = unique_username
    page.fill('input[name="search_query"]', search_keyword)
    with page.expect_navigation(url=re.compile(r"/search\?")):
        page.locator(".search-form").get_by_role("button", name="検索").click()

    # 3. 結果ページに「検索結果」見出しと、該当タイトルのリンクが見える
    expect(page.locator("h2", has_text="検索結果")).to_be_visible()
    expect(page.get_by_role("link", name=title)).to_be_visible()


def test_search_with_no_hits_shows_empty_message(
    page: Page,
    e2e_server_url: str,
) -> None:
    """絶対にヒットしないキーワードで検索し、空メッセージが出るか確認。"""
    page.goto(f"{e2e_server_url}/")
    # 実在しないキーワード（ランダム英数字＋00000）を入力
    page.fill('input[name="search_query"]', "no_such_keyword_xyz_00000")
    with page.expect_navigation(url=re.compile(r"/search\?")):
        page.locator(".search-form").get_by_role("button", name="検索").click()

    # 「該当する投稿が見つかりませんでした。」が画面に表示されているか
    expect(page.get_by_text("該当する投稿が見つかりませんでした。")).to_be_visible()

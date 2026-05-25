"""管理者ユーザーの作成または昇格を行う CLI スクリプト。

使用例:
    python -m app.scripts.grant_admin <username>

パスワードは環境変数 ``ADMIN_BOOTSTRAP_PASSWORD``（または .env）から読み込む。
- 既存ユーザーがいれば ``is_admin=True`` に更新するのみ（パスワードは変更しない）。
- 未登録なら新規作成し ``is_admin=True`` を付与する。
"""

import os  # 環境変数の読み取りに使う標準ライブラリ
import sys  # コマンドライン引数 (sys.argv) と異常終了 (sys.exit) で使う標準ライブラリ

from dotenv import (
    load_dotenv,
)  # .env ファイルを読み込んで環境変数化するライブラリ。dev 環境で SECRET_KEY などを管理するのに便利

# settings 読み込み前に .env を環境変数に展開
load_dotenv()  # .env を読み込んで os.environ に反映。app.db の import で settings が評価される前にやる必要がある

# load_dotenv() 後に import するのが必須なため、E402/I001 はファイル単位で抑止（pyproject.toml）
from app.db import SessionLocal, User
from app.routers.auth import hash_password


def grant_admin(
    username: str,
) -> None:  # -> None は「戻り値なし」の型ヒント。副作用 (DB 更新) のみの関数で使う
    """ユーザー名を受け取り、admin 化（または admin 付き新規作成）する."""
    bootstrap_password = os.environ.get(
        "ADMIN_BOOTSTRAP_PASSWORD"
    )  # .get() は未設定なら None を返す。os.environ[...] だと KeyError になるので安全な取得方法

    db = (
        SessionLocal()
    )  # DB セッションを生成。SessionLocal は app.db で定義されたセッションファクトリ
    try:  # try/finally で「成功失敗にかかわらず必ず close する」を保証 (リソースリーク防止)
        existing_user = (
            db.query(User).filter(User.username == username).first()
        )  # 同名ユーザーを検索。存在しなければ None が返る

        if existing_user:  # 既存ユーザーがいる分岐
            if existing_user.is_admin:  # 既に admin なら何もしない
                print(f"[skip] {username} は既に admin です")
                return
            existing_user.is_admin = (
                True  # ORM オブジェクトの属性を変更するだけで UPDATE 文の対象になる
            )
            db.commit()  # コミットしないと DB に反映されない。忘れがちな落とし穴
            print(f"[promote] {username} を admin に昇格しました")
            return

        # 新規作成にはパスワードが必須
        if (
            not bootstrap_password
        ):  # 環境変数が未設定なら新規作成不可。空文字列も None もここで弾ける
            print(
                "ADMIN_BOOTSTRAP_PASSWORD が未設定のため新規作成できません。"
                ".env に設定してから再実行してください。",
                file=sys.stderr,  # エラー系メッセージは標準エラー出力へ。標準出力と分けるとパイプ処理時に扱いやすい
            )
            sys.exit(1)  # 終了コード 1 = エラー終了。シェルスクリプト等から失敗を検知できる

        new_user = User(
            username=username,
            password=hash_password(
                bootstrap_password
            ),  # 必ずハッシュ化してから保存。平文保存は重大なセキュリティ事故になる
            is_admin=True,
        )
        db.add(new_user)  # セッションに登録。この時点ではまだ DB に書き込まれていない (保留状態)
        db.commit()  # ここで実際に INSERT 文が走る
        print(f"[create] {username} を admin として新規作成しました")
    finally:
        db.close()  # 例外が出ても確実にコネクションを返却。これを忘れると接続枯渇の原因になる


def main() -> None:
    if len(sys.argv) != 2:  # sys.argv[0] はスクリプト名なので、引数 1 個 = 全体で 2 要素という慣習
        print("Usage: python -m app.scripts.grant_admin <username>", file=sys.stderr)
        sys.exit(2)  # 終了コード 2 は慣例的に「使い方の誤り」を表す (1 と区別)
    grant_admin(sys.argv[1])  # 第一引数をユーザー名として渡す


if (
    __name__ == "__main__"
):  # このファイルが「直接実行された時だけ」main() を呼ぶ。import された時は実行されない定番イディオム
    main()

#!/usr/bin/env python3
r"""既存のアップロード画像から一括でサムネイルを生成するスクリプト。

担当: 運用・復旧用。app.py とは独立して実行し、static/uploads/ 内の画像から
     static/uploads/thumbs/ にサムネイルを生成する。

実行: project root で python generate_thumbs.py
オプション: --force で既存サムネイルを上書き
"""

import argparse
import os

from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
THUMBNAIL_DIR = os.path.join(UPLOAD_DIR, "thumbs")

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
THUMBNAIL_SIZE = (300, 300)


def make_thumbnail(source_path, destination_path):
    """担当: 1 ファイル分のサムネイル生成。成功 (True, None)、失敗 (False, エラーメッセージ)。"""
    try:
        with Image.open(source_path) as image:
            image.verify()
        # verify() 後は再 open しないと実体を扱えないため、もう一度開いて処理する
        with Image.open(source_path) as image:
            # JPEG 保存に備えて、透過モード (RGBA / P) は RGB に変換する
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            image.thumbnail(THUMBNAIL_SIZE)
            image.save(destination_path)
        return True, None
    except Exception as exception:
        return False, str(exception)


def main(force: bool = False):
    """担当: アップロードディレクトリを走査し、対象画像ごとに make_thumbnail を呼び出して結果を表示。"""
    if not os.path.isdir(UPLOAD_DIR):
        print(f"アップロードディレクトリが見つかりません: {UPLOAD_DIR}")
        return 1

    os.makedirs(THUMBNAIL_DIR, exist_ok=True)

    upload_filenames = [
        filename
        for filename in os.listdir(UPLOAD_DIR)
        if os.path.isfile(os.path.join(UPLOAD_DIR, filename))
    ]
    total_count = 0
    created_count = 0
    skipped_count = 0
    failed_count = 0

    for filename in upload_filenames:
        _, extension = os.path.splitext(filename)
        if extension.lower() not in SUPPORTED_EXTENSIONS:
            skipped_count += 1
            continue

        source_path = os.path.join(UPLOAD_DIR, filename)
        destination_path = os.path.join(THUMBNAIL_DIR, filename)
        total_count += 1

        if os.path.exists(destination_path) and not force:
            skipped_count += 1
            continue

        is_success, error_message = make_thumbnail(source_path, destination_path)
        if is_success:
            created_count += 1
            print(f"作成: {destination_path}")
        else:
            failed_count += 1
            print(f"失敗: {source_path} -> {error_message}")

    print("--- 処理結果 ---")
    print(f"対象画像: {total_count}")
    print(f"作成: {created_count}")
    print(f"スキップ: {skipped_count}")
    print(f"失敗: {failed_count}")
    return 0


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--force",
        action="store_true",
        help="既存サムネイルを上書きする",
    )
    parsed_arguments = argument_parser.parse_args()
    raise SystemExit(main(force=parsed_arguments.force))

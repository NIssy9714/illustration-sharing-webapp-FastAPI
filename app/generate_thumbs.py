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
THUMB_DIR = os.path.join(UPLOAD_DIR, "thumbs")

SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
THUMB_SIZE = (300, 300)


def make_thumbnail(src_path, dst_path):
    """担当: 1 ファイル分のサムネイル生成。成功 (True, None)、失敗 (False, エラーメッセージ)。"""
    try:
        with Image.open(src_path) as im:
            im.verify()
        # reopen to actually process
        with Image.open(src_path) as im:
            # convert transparent images to RGB for JPEGs
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.thumbnail(THUMB_SIZE)
            im.save(dst_path)
        return True, None
    except Exception as e:
        return False, str(e)


def main(force: bool = False):
    """担当: アップロードディレクトリを走査し、対象画像ごとに make_thumbnail を呼び出して結果を表示。"""
    if not os.path.isdir(UPLOAD_DIR):
        print(f"アップロードディレクトリが見つかりません: {UPLOAD_DIR}")
        return 1

    os.makedirs(THUMB_DIR, exist_ok=True)

    files = [
        f for f in os.listdir(UPLOAD_DIR) if os.path.isfile(os.path.join(UPLOAD_DIR, f))
    ]
    total = 0
    created = 0
    skipped = 0
    failed = 0

    for fn in files:
        _, ext = os.path.splitext(fn)
        if ext.lower() not in SUPPORTED_EXT:
            skipped += 1
            continue

        src = os.path.join(UPLOAD_DIR, fn)
        dst = os.path.join(THUMB_DIR, fn)
        total += 1

        if os.path.exists(dst) and not force:
            skipped += 1
            continue

        ok, err = make_thumbnail(src, dst)
        if ok:
            created += 1
            print(f"作成: {dst}")
        else:
            failed += 1
            print(f"失敗: {src} -> {err}")

    print("--- 処理結果 ---")
    print(f"対象画像: {total}")
    print(f"作成: {created}")
    print(f"スキップ: {skipped}")
    print(f"失敗: {failed}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="既存サムネイルを上書きする")
    args = p.parse_args()
    raise SystemExit(main(force=args.force))

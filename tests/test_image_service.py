"""image_service.py の単体テスト。

API 経由ではなく純粋関数として呼び出して、攻撃面（拡張子偽装・サイズ超過・
破損ファイル・メタデータ漏えい・モード不適合）を網羅する。

UploadFile / FileStorage を模した最小ダミーオブジェクトでテストする。
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.image_service import (
    DEFAULT_MAX_DIMENSIONS,
    allowed_file,
    process_uploaded_image,
)


class _DummyUpload:
    """UploadFile 互換の最小ダミー（filename / content_type / file を持つ）."""

    def __init__(self, filename: str, content_type: str, payload: bytes) -> None:
        self.filename = filename
        self.content_type = content_type
        self.file = io.BytesIO(payload)


def _png_bytes(width: int, height: int, mode: str = "RGB") -> bytes:
    """指定サイズ・モードの PNG をメモリ上で生成してバイト列で返す."""
    color: tuple[int, ...] = (0, 255, 0, 255) if mode == "RGBA" else (0, 255, 0)
    image = Image.new(mode, (width, height), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------------
# allowed_file: 拡張子ホワイトリスト
# ------------------------------------------------------------


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("a.png", True),
        ("a.JPG", True),  # 大文字も許可
        ("a.jpeg", True),
        ("a.gif", True),
        ("a.webp", True),
        ("a.bmp", False),  # 非許可拡張子
        ("a.exe", False),
        ("a.php.png", True),  # 末尾が png なら True（中身検証は別レイヤーの責務）
        ("noext", False),  # 拡張子なし
        ("", False),  # 空
    ],
)
def test_allowed_file_extension_whitelist(filename: str, expected: bool) -> None:
    """ALLOWED_EXTENSIONS に列挙された拡張子のみ True になる."""
    assert allowed_file(filename) is expected


# ------------------------------------------------------------
# process_uploaded_image: 正常系
# ------------------------------------------------------------


def test_valid_image_saved_with_uuid_filename(tmp_path: Path) -> None:
    """正常な PNG をアップロード → UUID ファイル名で保存され、サムネも生成される."""
    upload = _DummyUpload("hello.png", "image/png", _png_bytes(100, 100))

    filename, error = process_uploaded_image(
        upload,
        upload_base_dir=str(tmp_path),
    )

    assert error is None
    assert filename is not None
    # UUID + 拡張子の形式（hex 32 文字 + ".png"）
    assert filename.endswith(".png")
    assert len(filename) == len("0" * 32) + len(".png")
    # 本体ファイルとサムネイルファイルの両方が存在
    assert (tmp_path / filename).exists()
    assert (tmp_path / "thumbs" / filename).exists()


# ------------------------------------------------------------
# process_uploaded_image: 異常系（攻撃面）
# ------------------------------------------------------------


def test_oversized_image_rejected(tmp_path: Path) -> None:
    """最大寸法（4000x4000）を超える画像はエラー."""
    over_max_width, max_height = DEFAULT_MAX_DIMENSIONS[0] + 1, DEFAULT_MAX_DIMENSIONS[1]
    upload = _DummyUpload(
        "huge.png",
        "image/png",
        _png_bytes(over_max_width, max_height),
    )

    filename, error = process_uploaded_image(upload, upload_base_dir=str(tmp_path))

    assert filename is None
    assert error is not None
    assert "大きすぎます" in error


def test_wrong_mimetype_rejected(tmp_path: Path) -> None:
    """拡張子が png でも MIME タイプが image/* でなければ拒否（拡張子偽装対策）."""
    upload = _DummyUpload("evil.png", "text/plain", b"not an image")

    filename, error = process_uploaded_image(upload, upload_base_dir=str(tmp_path))

    assert filename is None
    assert error is not None
    # 本体ファイルは作成されないはず
    assert list(tmp_path.iterdir()) == []


def test_corrupt_bytes_rejected_by_pillow_verify(tmp_path: Path) -> None:
    """拡張子も MIME も画像装いだが、中身が壊れていれば Pillow verify で弾く."""
    # PNG マジックナンバーだけで以降ゴミバイト → verify が例外を投げる
    corrupt_payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
    upload = _DummyUpload("broken.png", "image/png", corrupt_payload)

    filename, error = process_uploaded_image(upload, upload_base_dir=str(tmp_path))

    assert filename is None
    assert error is not None
    # 本体ファイルは保存されない
    assert list(tmp_path.iterdir()) == []


# ------------------------------------------------------------
# process_uploaded_image: メタデータ・モード変換の不変条件
# ------------------------------------------------------------


def test_exif_metadata_is_stripped_on_save(tmp_path: Path) -> None:
    """EXIF を持つ JPEG をアップロード → 保存後ファイルに EXIF が残らないこと.

    位置情報や端末情報の漏えい防止。security commit (75e0754) で導入された不変条件。
    """
    # EXIF 付き JPEG を生成（Orientation タグだけ仕込む）
    image = Image.new("RGB", (100, 100), color=(0, 0, 255))
    exif = image.getexif()
    exif[0x0112] = 1  # Orientation = Normal（タグ自体が乗ることが重要）
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif.tobytes())
    upload = _DummyUpload("with_exif.jpg", "image/jpeg", buffer.getvalue())

    filename, error = process_uploaded_image(upload, upload_base_dir=str(tmp_path))
    assert error is None and filename is not None

    # 保存ファイルを開き直して EXIF が空であることを確認
    saved = Image.open(tmp_path / filename)
    assert dict(saved.getexif()) == {}, "EXIF が残ってはならない"


def test_rgba_image_converted_to_rgb_on_save(tmp_path: Path) -> None:
    """アルファ付き（RGBA）画像も保存・サムネ生成まで通り、RGB に変換されること."""
    upload = _DummyUpload("alpha.png", "image/png", _png_bytes(50, 50, mode="RGBA"))

    filename, error = process_uploaded_image(upload, upload_base_dir=str(tmp_path))

    assert error is None and filename is not None
    saved = Image.open(tmp_path / filename)
    # PNG なので RGB / RGBA どちらも保存可能だが、_ensure_saveable_mode で RGB 化される
    assert saved.mode == "RGB"
    # サムネも同様に生成完了
    assert (tmp_path / "thumbs" / filename).exists()


# ------------------------------------------------------------
# 入力欠落系
# ------------------------------------------------------------


def test_none_upload_returns_error(tmp_path: Path) -> None:
    """file_storage=None は明示的にエラーメッセージを返す."""
    filename, error = process_uploaded_image(None, upload_base_dir=str(tmp_path))
    assert filename is None
    assert error == "画像ファイルが選択されていません"


def test_empty_filename_returns_error(tmp_path: Path) -> None:
    """空ファイル名は拡張子チェック前に弾かれる."""
    upload = _DummyUpload("", "image/png", b"")
    filename, error = process_uploaded_image(upload, upload_base_dir=str(tmp_path))
    assert filename is None
    assert error == "画像ファイルが選択されていません"

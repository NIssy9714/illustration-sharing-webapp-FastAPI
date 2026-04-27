"""
画像アップロード・検証・保存・サムネイル生成を行うサービスモジュール。

担当: 拡張子・MIME・Pillow 検証、保存、サムネイル生成。
"""

import os
import re
import uuid

from PIL import Image, ImageOps

from app.core.logging import get_logger

log = get_logger("app.image_service")


def _secure_filename(filename: str) -> str:
    """ファイル名から危険な文字を除去（werkzeug.secure_filename 相当の最小実装）."""
    filename = os.path.basename(filename)
    filename = filename.replace("\\", "_").replace("/", "_")
    filename = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    return filename.strip("._") or "file"


# 許可する拡張子
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# デフォルトの画像サイズ上限（幅・高さ）
DEFAULT_MAX_DIMENSIONS = (4000, 4000)

# デフォルトのサムネイルサイズ
DEFAULT_THUMBNAIL_SIZE = (300, 300)


def allowed_file(filename: str) -> bool:
    """拡張子が許可リストに含まれるか判定."""
    if not filename or "." not in filename:
        return False
    file_extension = filename.rsplit(".", 1)[1].lower()
    return file_extension in ALLOWED_EXTENSIONS


def _verify_image(stream) -> Image.Image:
    """Pillow で open + verify() により画像の正当性を検証し、検証済みの Image を返す。

    `verify()` は遅延読み込みの状態でしか使えないため、検証後は再 open して `load()` する。
    EXIF Orientation も自動適用してピクセルデータを正立した状態にする。
    """
    stream.seek(0)
    image = Image.open(stream)
    image.verify()
    stream.seek(0)
    image = Image.open(stream)
    image.load()  # 遅延ロードを強制（後続の copy/save が確実に動作する）
    # スマホ撮影写真などで EXIF Orientation が指定されている場合に正立させる
    image = ImageOps.exif_transpose(image)
    return image


def _ensure_saveable_mode(image: Image.Image) -> Image.Image:
    """RGBA/P などを保存可能なモード（RGB）に変換."""
    if image.mode in ("RGBA", "P"):
        return image.convert("RGB")
    return image


def _save_image(image: Image.Image, filepath: str) -> None:
    """画像を指定パスに保存（モード変換は _ensure_saveable_mode に委譲）."""
    image_to_save = _ensure_saveable_mode(image)
    image_to_save.save(filepath)


def create_thumbnail(
    image: Image.Image,
    thumbnail_dir: str,
    filename: str,
    size: tuple[int, int] = DEFAULT_THUMBNAIL_SIZE,
) -> str:
    """指定サイズのサムネイルを生成し、保存先パスを返す."""
    os.makedirs(thumbnail_dir, exist_ok=True)
    thumbnail_path = os.path.join(thumbnail_dir, filename)
    thumb = image.copy()
    thumb.thumbnail(size)
    if thumb.mode in ("RGBA", "P"):
        thumb = thumb.convert("RGB")
    thumb.save(thumbnail_path)
    return thumbnail_path


def process_uploaded_image(
    file_storage,
    upload_base_dir: str = "static/uploads",
    max_dimensions: tuple[int, int] = DEFAULT_MAX_DIMENSIONS,
    thumbnail_size: tuple[int, int] = DEFAULT_THUMBNAIL_SIZE,
) -> tuple[str | None, str | None]:
    """アップロード画像の検証・保存・サムネイル生成を一括で行う。

    成功時 (ファイル名, None)、失敗時 (None, エラーメッセージ)。
    本体保存に成功したあとサムネ生成に失敗した場合は警告ログを出すが、
    投稿自体は成功させる（テンプレート側で onerror により本体画像にフォールバック）。
    """
    if file_storage is None:
        return None, "画像ファイルが選択されていません"

    filename_original = getattr(file_storage, "filename", "") or ""
    if not filename_original.strip():
        return None, "画像ファイルが選択されていません"

    if not allowed_file(filename_original):
        return None, "画像ファイル（png,jpg,jpeg,gif,webp）をアップロードしてください"

    mimetype = getattr(file_storage, "content_type", None) or getattr(
        file_storage,
        "mimetype",
        None,
    )
    if not (mimetype and mimetype.startswith("image/")):
        return None, "画像ファイルをアップロードしてください"

    safe_name = _secure_filename(filename_original)
    _, ext = os.path.splitext(safe_name)
    filename = f"{uuid.uuid4().hex}{ext.lower()}"
    filepath = os.path.join(upload_base_dir, filename)

    # FastAPI の UploadFile は .file、Flask の FileStorage は .stream を持つ。両対応。
    stream = getattr(file_storage, "file", None) or getattr(file_storage, "stream", None)
    if stream is None:
        return None, "有効な画像ファイルをアップロードしてください"

    try:
        image = _verify_image(stream)
    except Exception as e:
        log.warning("image.verify_failed", filename=filename_original, error=str(e))
        return None, "有効な画像ファイルをアップロードしてください"

    max_w, max_h = max_dimensions
    if image.width > max_w or image.height > max_h:
        return None, f"画像のサイズが大きすぎます（最大 {max_w}x{max_h}）。"

    os.makedirs(upload_base_dir, exist_ok=True)

    try:
        _save_image(image, filepath)
    except Exception as e:
        log.warning("image.save_failed", filepath=filepath, error=str(e))
        return None, "有効な画像ファイルをアップロードしてください"

    thumbnail_dir = os.path.join(upload_base_dir, "thumbs")
    try:
        thumb_path = create_thumbnail(image, thumbnail_dir, filename, thumbnail_size)
        log.info("thumbnail.created", filename=filename, path=thumb_path)
    except Exception as e:
        # サムネ失敗は本体表示の onerror フォールバックでカバー。原因は必ずログに残す。
        log.warning(
            "thumbnail.create_failed",
            filename=filename,
            error=str(e),
            mode=image.mode,
            size=image.size,
        )

    return filename, None

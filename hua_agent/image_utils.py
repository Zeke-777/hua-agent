"""Image upload validation utilities."""

import os

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB

_MAGIC_SIGNATURES = {
    (0xFF, 0xD8): ".jpg",
    (0x89, 0x50, 0x4E, 0x47): ".png",
    (0x47, 0x49, 0x46): ".gif",
    (0x52, 0x49, 0x46, 0x46): ".webp",
}


def detect_type_by_magic(data: bytes) -> str | None:
    """Detect image type from magic bytes. Returns extension or None."""
    if len(data) < 16:
        return None
    for magic, ext in _MAGIC_SIGNATURES.items():
        if data[: len(magic)] == bytes(magic):
            return ext
    return None


def validate_upload(filename: str | None, content_type: str | None, body: bytes) -> str:
    """Validate uploaded image and return normalized extension. Raises HTTPException."""
    from fastapi import HTTPException

    if not filename:
        raise HTTPException(status_code=400, detail="文件名为空")
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}")
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {content_type}")
    if len(body) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    detected_ext = detect_type_by_magic(body)
    if detected_ext is None:
        raise HTTPException(status_code=400, detail="无法识别文件格式")
    if detected_ext != ext and not (ext == ".jpeg" and detected_ext == ".jpg"):
        raise HTTPException(status_code=400, detail="文件内容与扩展名不匹配")
    return ext

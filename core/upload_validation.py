"""Shared upload validation for OCR and document endpoints."""

from django.core.exceptions import ValidationError

OCR_MAX_BYTES = 5 * 1024 * 1024
OCR_ALLOWED_CONTENT_TYPES = frozenset({
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "application/pdf",
})
OCR_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf"})


def validate_ocr_upload(file_obj):
    if not file_obj:
        raise ValidationError("No file uploaded.")
    size = getattr(file_obj, "size", None)
    if size is not None and size > OCR_MAX_BYTES:
        raise ValidationError("File is too large. Maximum size is 5 MB.")
    content_type = (getattr(file_obj, "content_type", "") or "").lower()
    name = (getattr(file_obj, "name", "") or "").lower()
    ext = ""
    if "." in name:
        ext = name[name.rfind(".") :]
    if content_type and content_type not in OCR_ALLOWED_CONTENT_TYPES:
        if ext not in OCR_ALLOWED_EXTENSIONS:
            raise ValidationError("Unsupported file type for OCR.")
    elif not content_type and ext not in OCR_ALLOWED_EXTENSIONS:
        raise ValidationError("Unsupported file type for OCR.")

"""Render wallet documents (especially PDFs) to PNG previews for the mobile app."""

from __future__ import annotations

import io
import logging
import mimetypes
import os
from typing import Optional, Tuple

from django.core.files.base import File
from django.http import HttpResponse

logger = logging.getLogger(__name__)

MAX_PDF_PAGES = 8
PREVIEW_ZOOM = 2.0  # ~144 DPI-equivalent clarity for ID cards


def _is_pdf_name(name: str) -> bool:
    lower = (name or "").lower()
    return lower.endswith(".pdf") or "pdf" in (mimetypes.guess_type(name)[0] or "")


def _is_image_name(name: str) -> bool:
    mime, _ = mimetypes.guess_type(name or "")
    return bool(mime and mime.startswith("image/"))


def _read_file_bytes(file_field: File) -> bytes:
    file_field.open("rb")
    try:
        return file_field.read()
    finally:
        try:
            file_field.close()
        except Exception:
            pass


def _sniff_pdf(data: bytes) -> bool:
    return bool(data) and data[:5] == b"%PDF-"


def render_pdf_pages_to_png(data: bytes, *, max_pages: int = MAX_PDF_PAGES) -> Tuple[bytes, int]:
    """
    Rasterize PDF pages into a single vertical PNG (page 1..N).
    Returns (png_bytes, page_count_rendered).
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("PDF preview requires pymupdf") from exc

    from PIL import Image

    doc = fitz.open(stream=data, filetype="pdf")
    try:
        total = doc.page_count or 0
        if total <= 0:
            raise ValueError("Empty PDF")
        pages_to_render = min(total, max_pages)
        mats = []
        matrix = fitz.Matrix(PREVIEW_ZOOM, PREVIEW_ZOOM)
        for index in range(pages_to_render):
            page = doc.load_page(index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            mats.append(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))

        if len(mats) == 1:
            out = io.BytesIO()
            mats[0].save(out, format="PNG", optimize=True)
            return out.getvalue(), pages_to_render

        width = max(im.width for im in mats)
        gap = 12
        height = sum(im.height for im in mats) + gap * (len(mats) - 1)
        canvas = Image.new("RGB", (width, height), (248, 250, 252))
        y = 0
        for im in mats:
            x = (width - im.width) // 2
            canvas.paste(im, (x, y))
            y += im.height + gap
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        return out.getvalue(), pages_to_render
    finally:
        doc.close()


def render_image_to_png(data: bytes, filename: str = "") -> bytes:
    """Normalize any common image upload to PNG for consistent mobile display."""
    from PIL import Image, ImageOps

    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    # Cap extremely large scans while keeping ID-card detail.
    max_edge = 2200
    if max(im.size) > max_edge:
        im.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    if im.mode == "RGBA":
        background = Image.new("RGB", im.size, (255, 255, 255))
        background.paste(im, mask=im.split()[-1])
        background.save(out, format="PNG", optimize=True)
    else:
        im.convert("RGB").save(out, format="PNG", optimize=True)
    return out.getvalue()


def build_document_preview_response(file_field: File) -> HttpResponse:
    """
    Always return an image/png preview of the uploaded document content.
    PDFs are rasterized (pages stacked). Images are normalized to PNG.
    """
    filename = os.path.basename(getattr(file_field, "name", "") or "document")
    data = _read_file_bytes(file_field)
    if not data:
        raise ValueError("Empty file")

    png: Optional[bytes] = None
    pages = 1
    source = "image"

    if _sniff_pdf(data) or _is_pdf_name(filename):
        source = "pdf"
        png, pages = render_pdf_pages_to_png(data)
    elif _is_image_name(filename) or data[:8].startswith(b"\x89PNG") or data[:3] == b"\xff\xd8\xff" or data[:6] in (b"GIF87a", b"GIF89a"):
        png = render_image_to_png(data, filename)
    else:
        # Last resort: try PDF open, then image open.
        try:
            png, pages = render_pdf_pages_to_png(data)
            source = "pdf"
        except Exception:
            png = render_image_to_png(data, filename)
            source = "image"

    response = HttpResponse(png, content_type="image/png")
    response["Content-Disposition"] = f'inline; filename="{os.path.splitext(filename)[0] or "preview"}.png"'
    response["X-File-Name"] = f"{os.path.splitext(filename)[0] or 'preview'}.png"
    response["X-Preview-Source"] = source
    response["X-Preview-Pages"] = str(pages)
    response["Cache-Control"] = "private, max-age=120"
    return response

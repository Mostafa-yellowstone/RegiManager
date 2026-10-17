"""OCR authentication and OCR.space integration."""

import io
import os
from concurrent.futures import ThreadPoolExecutor

import requests

OCR_SPACE_URL = "https://api.ocr.space/parse/image"
# OCR.space rejects uploads over 1 MB on the free plan, so scanned pages are re-encoded under that.
OCR_MAX_UPLOAD_BYTES = 1_000_000


def check_ocr_auth(request):
    if request.user.is_authenticated:
        return True
    portal_token = request.POST.get("portal_token")
    if not portal_token:
        return False
    from .models import Organization

    return Organization.objects.filter(
        portal_token=portal_token,
        is_active=True,
        is_public_intake_enabled=True,
    ).exists()


def perform_ocr(file_obj):
    """Robust OCR wrapper for OCR.space with Engine 2 -> Engine 1 fallback."""
    api_key = os.environ.get("OCR_API_KEY")
    if not api_key:
        return False, "OCR is not configured on this server."

    try:
        payload = {
            "isOverlayRequired": False,
            "apikey": api_key,
            "language": "eng",
            "OCREngine": 2,
            "scale": True,
        }
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": file_obj},
            data=payload,
            timeout=20,
        )
        result = response.json()
        if result.get("OCRExitCode") == 1:
            parsed = result.get("ParsedResults")
            if parsed and parsed[0].get("ParsedText"):
                return True, parsed[0].get("ParsedText")
    except Exception:
        pass

    try:
        file_obj.seek(0)
        payload = {
            "isOverlayRequired": False,
            "apikey": api_key,
            "language": "eng",
            "OCREngine": 1,
            "detectOrientation": True,
            "scale": True,
        }
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": file_obj},
            data=payload,
            timeout=20,
        )
        result = response.json()
        if result.get("OCRExitCode") == 1:
            parsed = result.get("ParsedResults")
            if parsed and parsed[0].get("ParsedText"):
                return True, parsed[0].get("ParsedText")

        err = result.get("ErrorMessage") or "OCR Failed"
        if isinstance(err, list):
            err = ", ".join(err)
        return False, err
    except Exception as exc:
        return False, str(exc)


def _ocr_page_image(api_key, image_bytes):
    """OCR one page image. Table mode keeps each printed row on one line, which the DEC parsers rely on."""
    last_error = "OCR failed"
    for engine in (2, 1):
        try:
            response = requests.post(
                OCR_SPACE_URL,
                files={"file": ("page.jpg", image_bytes, "image/jpeg")},
                data={
                    "apikey": api_key,
                    "language": "eng",
                    "OCREngine": engine,
                    "isTable": True,
                    "scale": True,
                    "detectOrientation": True,
                    "filetype": "JPG",
                },
                timeout=40,
            )
            result = response.json()
        except Exception as exc:
            last_error = str(exc)
            continue
        parsed = result.get("ParsedResults") or []
        text = (parsed[0].get("ParsedText") or "") if parsed else ""
        if result.get("OCRExitCode") in (1, 2) and text.strip():
            return True, text
        err = result.get("ErrorMessage") or last_error
        last_error = ", ".join(err) if isinstance(err, list) else str(err)
    return False, last_error


def _render_pdf_pages(pdf_bytes, max_pages, dpi):
    import fitz
    from PIL import Image

    images = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in list(doc)[:max_pages]:
            pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
            image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            for quality in (85, 70, 55, 40):
                buffer = io.BytesIO()
                image.save(buffer, "JPEG", quality=quality, optimize=True)
                if buffer.tell() <= OCR_MAX_UPLOAD_BYTES:
                    break
            images.append(buffer.getvalue())
    return images


def ocr_pdf_text(pdf_bytes, *, max_pages=6, dpi=200):
    """
    Read text from an image-only PDF (scans, "Microsoft Print to PDF" of a picture).

    Returns (ok, text_or_error). Pages are OCR'd in parallel and joined in page order.
    """
    api_key = os.environ.get("OCR_API_KEY")
    if not api_key:
        return False, "OCR is not configured on this server (OCR_API_KEY is missing)."
    try:
        images = _render_pdf_pages(pdf_bytes, max_pages, dpi)
    except Exception as exc:
        return False, f"Could not render PDF pages for OCR: {exc}"
    if not images:
        return False, "The PDF has no pages."

    with ThreadPoolExecutor(max_workers=min(4, len(images))) as pool:
        results = list(pool.map(lambda data: _ocr_page_image(api_key, data), images))
    pages = [text for ok, text in results if ok]
    if not pages:
        return False, results[0][1]
    return True, "\n".join(pages)

"""OCR authentication and OCR.space integration."""

import os

import requests


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

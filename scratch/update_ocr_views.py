import re

path = 'core/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add the auth helper right before ocr_dl_ajax
auth_helper = '''def _check_ocr_auth(request):
    if request.user.is_authenticated:
        return True
    portal_token = request.POST.get("portal_token")
    if portal_token and Organization.objects.filter(portal_token=portal_token, is_active=True).exists():
        return True
    return False

@require_POST
def ocr_dl_ajax(request):
    if not _check_ocr_auth(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)'''

content = re.sub(
    r'@login_required\s*@require_POST\s*def ocr_dl_ajax\(request\):',
    auth_helper,
    content
)

old_title_ajax = r'''@login_required\s*@require_POST\s*def ocr_vehicle_title_ajax\(request\):.*?return JsonResponse\(\{"status": "success", "data": data\}\)'''

new_title_ajax = r'''@require_POST
def ocr_vehicle_title_ajax(request):
    """
    Title/barcode scan parser for vehicle autofill.
    Works with handheld scanner text payload OR image file upload via OCR.space.
    """
    if not _check_ocr_auth(request):
        return JsonResponse({"status": "error", "message": "Unauthorized"}, status=401)
        
    import re
    data = {}

    raw = (request.POST.get("scan_data") or "").strip().upper()

    if 'file' in request.FILES:
        import requests
        file_obj = request.FILES['file']
        try:
            payload = {
                'isOverlayRequired': False,
                'apikey': 'helloworld',
                'language': 'eng',
                'OCREngine': 2,
            }
            r = requests.post('https://api.ocr.space/parse/image',
                            files={'file': file_obj},
                            data=payload,
                            timeout=15)
            result = r.json()
            if result.get('OCRExitCode') == 1:
                raw = result.get('ParsedResults')[0].get('ParsedText').upper()
            else:
                return JsonResponse({"status": "error", "message": "OCR failed: " + str(result.get('ErrorMessage'))})
        except Exception as e:
            return JsonResponse({"status": "error", "message": "OCR Error: " + str(e)})

    if not raw:
        return JsonResponse({"status": "error", "message": "Missing scan data or image."}, status=400)

    # VIN: 17 chars excluding I/O/Q
    vin_match = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", raw)
    if vin_match:
        data["vin"] = vin_match.group(1)

    year_match = re.search(r"\b(19[8-9]\d|20[0-4]\d)\b", raw)
    if year_match:
        data["year"] = year_match.group(1)

    # Heuristic key-value extraction common in scanner dumps and OCR output
    def extract_after(label):
        m = re.search(rf"{label}\s*[:\-]?\s*([A-Z0-9 ]{{2,40}})", raw)
        return m.group(1).strip() if m else ""

    make = extract_after("MAKE")
    model = extract_after("MODEL")
    plate = extract_after("PLATE")
    
    # Also look for common keywords if explicit labels aren't found
    if not make:
        makes = ["TOYOTA", "HONDA", "FORD", "CHEVROLET", "NISSAN", "BMW", "MERCEDES", "AUDI", "VOLKSWAGEN", "JEEP", "SUBARU", "HYUNDAI", "KIA", "DODGE", "GMC", "LEXUS", "MAZDA"]
        for m in makes:
            if m in raw:
                make = m
                break

    if make:
        data["make"] = make
    if model:
        data["model"] = model
    if plate:
        data["plate_number"] = plate

    if 'file' in request.FILES and not data:
        data = {"status_msg": "Image processed but no clear vehicle data found. Please fill manually.", "raw_text": raw[:100]}

    return JsonResponse({"status": "success", "data": data})'''

# find the match
m = re.search(old_title_ajax, content, flags=re.DOTALL)
if m:
    content = content[:m.start()] + new_title_ajax + content[m.end():]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated views.py")
else:
    print("Match not found")

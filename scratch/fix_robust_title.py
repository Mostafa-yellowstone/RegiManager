import re

path = 'core/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = "    # 1. VIN (17 chars)"
end_marker = "    if 'file' in request.FILES and not data:"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_block = """    # 1. VIN (17 chars) - Handle OCR misreading 1 as L
    vin_match = re.search(r"\\b([1A-HJ-NPR-Z0-9]{17}|[L][A-HJ-NPR-Z0-9]{16})\\b", raw)
    if vin_match:
        vin = vin_match.group(1)
        if vin.startswith('L'): # Common OCR error for NY titles
             vin = '1' + vin[1:]
        data["vin"] = vin

    # 2. Year (4 digits)
    year_match = re.search(r"\\b(19\\d{2}|20\\d{2})\\b", raw)
    if year_match:
        data["year"] = year_match.group(1)

    # 3. Make (Common NY Abbreviations)
    makes_map = {
        "CHEVR": "CHEVROLET", "TOYOT": "TOYOTA", "HONDA": "HONDA", "FORD": "FORD", 
        "NISSA": "NISSAN", "BMW": "BMW", "MERCE": "MERCEDES-BENZ", "VOLKS": "VOLKSWAGEN",
        "DODGE": "DODGE", "GMC": "GMC", "LEXUS": "LEXUS", "MAZDA": "MAZDA", 
        "SUBAR": "SUBARU", "HYUND": "HYUNDAI", "KIA": "KIA", "JEEP": "JEEP",
        "CHRYSL": "CHRYSLER", "ACURA": "ACURA", "INFIN": "INFINITI", "AUDI": "AUDI",
        "CADIL": "CADILLAC", "BUICK": "BUICK", "RAM": "RAM", "LINCO": "LINCOLN"
    }
    for code, full in makes_map.items():
        if code in raw:
            data["make"] = full
            break

    # 4. Color (2 chars)
    color_map = {
        "GY": "GRAY", "WH": "WHITE", "BK": "BLACK", "BL": "BLUE", "RD": "RED", 
        "SL": "SILVER", "BR": "BROWN", "GR": "GREEN", "OR": "ORANGE", "YW": "YELLOW", 
        "PR": "PURPLE", "TN": "TAN", "GD": "GOLD", "MR": "MAROON"
    }
    # Look for the color code, usually near 'COLOR' or on its own line
    color_match = re.search(r"\\b(GY|WH|BK|BL|RD|SL|BR|GR|OR|YW|PR|TN|GD|MR)\\b", raw)
    if color_match:
        data["color"] = color_map.get(color_match.group(1))

    # 5. Cylinders
    cyl_match = re.search(r"(?:CYL|PROP)\\.?\\s*(\\d+)", raw)
    if not cyl_match: # Fallback: search for single digit near the word CYL
        cyl_match = re.search(r"CYL[\\s\\S]{1,20}?\\b(\\d)\\b", raw)
    if cyl_match:
        data["cylinders"] = cyl_match.group(1)

    # 6. Weight (Usually 4 digits, near WT)
    weight_match = re.search(r"(?:WT|LGTH)\\.?\\s*(\\d{3,5})", raw)
    if not weight_match:
        # Fallback: look for 4 digits that are NOT the year
        all_nums = re.findall(r"\\b(\\d{4})\\b", raw)
        for num in all_nums:
            if num != data.get("year"):
                data["weight"] = num
                break
    else:
        data["weight"] = weight_match.group(1)

    # 7. Fuel
    fuel_match = re.search(r"\\b(GAS|DSL|HYB|ELE|G)\\b", raw)
    if fuel_match:
        f_val = fuel_match.group(1)
        data["fuel_type"] = "GAS" if f_val in ("GAS", "G") else f_val

    # 8. Model (Heuristic)
    if not data.get("model"):
        # Look for the word after MAKE in the raw text
        words = raw.split()
        for i, word in enumerate(words):
            if word == "MAKE" and i + 1 < len(words):
                # The value might be several lines down, but let's check nearby words
                pass
        # Better heuristic: look for 3-letter codes like SLV, SUV, PICK
        model_match = re.search(r"\\b(SLV|SUV|PICK|4DSD|2DSD|SUBN|TRAC|VAN)\\b", raw)
        if model_match:
            data["model"] = model_match.group(1)
"""
    
    content = content[:start_idx] + new_block + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated views.py successfully")
else:
    print("Could not find markers")

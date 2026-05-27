import re

path = 'core/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = "                # Advanced parser for New York State and standard DLs"
end_marker = "                # 3. Fallbacks if strict parsing missed"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    old_block = content[start_idx:end_idx]
    
    new_block = """                # Advanced parser for New York State and standard DLs
                lines = [l.strip() for l in text.split('\\n') if l.strip()]
                
                # Forward pass: just extract ID
                for i, line in enumerate(lines):
                    upper_line = line.upper()
                    if 'ID ' in upper_line or upper_line.startswith('ID'):
                        id_match = re.search(r'ID\\s*([A-Z0-9\\s]{9,15})', upper_line)
                        if id_match:
                            clean_id = id_match.group(1).replace(' ', '')
                            clean_id = re.sub(r'[^A-Z0-9]', '', clean_id)
                            if len(clean_id) >= 9:
                                data['driver_license'] = clean_id[:9]

                # Reverse pass from DOB
                dob_index = -1
                for i, line in enumerate(lines):
                    if 'DOB' in line.upper():
                        dob_match = re.search(r'(\\d{2}/\\d{2}/\\d{4})', line)
                        if dob_match:
                            dob_index = i
                            d_str = dob_match.group(1)
                            parts = d_str.split('/')
                            data['dob'] = f"{parts[2]}-{parts[0]}-{parts[1]}"
                            break

                if dob_index != -1:
                    # Parse backward from DOB
                    # Index - 1: City, State Zip
                    if dob_index - 1 >= 0:
                        addr_line2 = lines[dob_index - 1]
                        csz_match = re.search(r'^(.+?)[,\\s]+([A-Za-z]{2})\\s+(\\d{5}(?:-\\d{4})?)', addr_line2)
                        if csz_match:
                            data['city'] = csz_match.group(1).strip()
                            data['state'] = csz_match.group(2).strip().upper()
                            data['zip_code'] = csz_match.group(3).strip()
                            
                            if data['state'] == 'NY':
                                city_upper = data['city'].upper()
                                zip_start = data['zip_code'][:3]
                                if city_upper == 'YONKERS' or zip_start in ('105', '106', '107', '108'):
                                    data['county'] = 'Westchester'

                    # Index - 2: Street Address
                    if dob_index - 2 >= 0:
                        addr_line1 = lines[dob_index - 2]
                        bno_match = re.search(r'^(\\d+)\\s+(.+)$', addr_line1)
                        if bno_match:
                            data['building_no'] = bno_match.group(1)
                            rest_of_street = bno_match.group(2)
                            apt_match = re.search(r'(?i)\\s+(APT|#|UNIT|STE|SUITE|APARTMENT)\\s+(.+)$', rest_of_street)
                            if apt_match:
                                data['street_address'] = rest_of_street[:apt_match.start()].strip()
                                data['apartment'] = f"{apt_match.group(1).upper()} {apt_match.group(2).strip()}"
                            else:
                                data['street_address'] = rest_of_street
                        else:
                            data['street_address'] = addr_line1

                    # Index - 3: First Name, Middle Name
                    if dob_index - 3 >= 0:
                        # Clean up "BRITNEY, GUADALUPE"
                        name_line = lines[dob_index - 3]
                        # sometimes OCR misses the comma if space is small, but let's assume comma or space
                        names = [n.strip() for n in name_line.replace('FIRST', '').replace('NAME', '').split(',')]
                        if len(names) == 1 and ' ' in names[0]:
                            names = names[0].split(' ', 1)
                        data['first_name'] = names[0].strip()
                        if len(names) > 1:
                            data['middle_name'] = names[1].strip()

                    # Index - 4: Last Name
                    if dob_index - 4 >= 0:
                        data['last_name'] = lines[dob_index - 4].replace('LAST', '').replace('NAME', '').strip()

"""
    
    content = content[:start_idx] + new_block + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated views.py successfully")
else:
    print("Could not find markers")

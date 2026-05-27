import re

path = 'core/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = "                # Advanced parser for New York State and standard DLs"
end_marker = "                # 3. Fallbacks if strict parsing missed"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)

if start_idx != -1 and end_idx != -1:
    new_block = """                # Advanced parser for New York State and standard DLs
                lines = [l.strip() for l in text.split('\\n') if l.strip()]
                
                # 1. Driver License
                # Notice in the raw text it might be 'Đ 729 264 610', so look for 9 digits grouped.
                dl_match = re.search(r'\\b(?:ID\\s*|\\w\\s+)?(\\d{3}\\s?\\d{3}\\s?\\d{3})\\b', text)
                if dl_match:
                    data['driver_license'] = dl_match.group(1).replace(' ', '')
                
                # 2. DOB (Notice raw text has 'ров 01/03/2002' instead of DOB)
                dob_match = re.search(r'(\\d{2}/\\d{2}/\\d{4})', text)
                if dob_match:
                    parts = dob_match.group(1).split('/')
                    data['dob'] = f"{parts[2]}-{parts[0]}-{parts[1]}"
                    
                # 3. Use City, State, Zip as the Anchor for Address and Names
                csz_index = -1
                for i, line in enumerate(lines):
                    csz_match = re.search(r'^(.+?)[,\\s]+([A-Za-z]{2})\\s+(\\d{5}(?:-\\d{4})?)', line)
                    if csz_match:
                        csz_index = i
                        data['city'] = csz_match.group(1).strip()
                        data['state'] = csz_match.group(2).strip().upper()
                        data['zip_code'] = csz_match.group(3).strip()
                        
                        if data['state'] == 'NY':
                            city_upper = data['city'].upper()
                            zip_start = data['zip_code'][:3]
                            if city_upper == 'YONKERS' or zip_start in ('105', '106', '107', '108'):
                                data['county'] = 'Westchester'
                            elif zip_start in ('100', '101', '102'):
                                data['county'] = 'New York'
                            elif zip_start == '103':
                                data['county'] = 'Richmond'
                            elif zip_start == '104':
                                data['county'] = 'Bronx'
                            elif zip_start in ('110', '114', '111', '113', '116'):
                                data['county'] = 'Queens'
                            elif zip_start == '112':
                                data['county'] = 'Kings'
                        break

                if csz_index != -1:
                    # Index - 1: Street Address
                    if csz_index - 1 >= 0:
                        addr_line1 = lines[csz_index - 1]
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

                    # Index - 2: First Name, Middle Name
                    if csz_index - 2 >= 0:
                        name_line = lines[csz_index - 2]
                        names = [n.strip() for n in name_line.replace('FIRST', '').replace('NAME', '').split(',')]
                        if len(names) == 1 and ' ' in names[0]:
                            names = names[0].split(' ', 1)
                        if len(names) > 0 and names[0]:
                            data['first_name'] = names[0].strip()
                        if len(names) > 1:
                            data['middle_name'] = names[1].strip()

                    # Index - 3: Last Name
                    if csz_index - 3 >= 0:
                        data['last_name'] = lines[csz_index - 3].replace('LAST', '').replace('NAME', '').strip()

"""
    
    content = content[:start_idx] + new_block + content[end_idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated views.py successfully")
else:
    print("Could not find markers")

import re

path = 'core/views.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_logic = r"""                                if i \+ 2 < len\(lines\):
                                    # Split by comma \(e.g. BRITNEY,GUADALUPE\)
                                    names = lines\[i\+2\].replace\('FIRST', ''\).replace\('NAME', ''\).split\(','\)
                                    data\['first_name'\] = names\[0\].strip\(\)
                                    if len\(names\) > 1:
                                        data\['middle_name'\] = names\[1\].strip\(\)"""

new_logic = """                                if i + 2 < len(lines):
                                    # Split by comma (e.g. BRITNEY,GUADALUPE)
                                    names = lines[i+2].replace('FIRST', '').replace('NAME', '').split(',')
                                    data['first_name'] = names[0].strip()
                                    if len(names) > 1:
                                        data['middle_name'] = names[1].strip()

                                # Address Line 1 (e.g. 31 ALDER ST APT 2R)
                                if i + 3 < len(lines):
                                    addr_line1 = lines[i+3].strip()
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

                                # Address Line 2 (e.g. YONKERS, NY 10701)
                                if i + 4 < len(lines):
                                    addr_line2 = lines[i+4].strip()
                                    csz_match = re.search(r'^(.+?)[,\\s]+([A-Za-z]{2})\\s+(\\d{5}(?:-\\d{4})?)$', addr_line2)
                                    if csz_match:
                                        data['city'] = csz_match.group(1).strip()
                                        data['state'] = csz_match.group(2).strip().upper()
                                        data['zip_code'] = csz_match.group(3).strip()
                                        
                                        # Simple county heuristic for NY
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
                                            elif zip_start in ('115', '117', '118', '119'):
                                                # Could be Nassau or Suffolk, let's leave blank or rough guess
                                                pass"""

# Find and replace
m = re.search(old_logic, content)
if m:
    content = content[:m.start()] + new_logic + content[m.end():]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Updated views.py successfully")
else:
    print("Match not found")

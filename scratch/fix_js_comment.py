path = 'templates/core/outstanding_balances.html'

with open(path, encoding='utf-8') as f:
    lines = f.readlines()

# Line 498 (0-indexed: 497) contains a bare {% url %} inside a JS comment
# Replace just that line
target_idx = 497  # 0-indexed

old_line = lines[target_idx]
print(f'Line 498 before: {repr(old_line.rstrip())}')

# Remove the {% url %} tag from the comment text so Django doesn't parse it
new_line = old_line.replace('{% url %}', 'url tag')
lines[target_idx] = new_line
print(f'Line 498 after:  {repr(new_line.rstrip())}')

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Done.')

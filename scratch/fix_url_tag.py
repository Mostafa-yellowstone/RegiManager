import sys

path = 'templates/core/outstanding_balances.html'

with open(path, encoding='utf-8') as f:
    raw = f.read()

fixes = [
    # Fix 1: Back-to-dashboard link
    (
        "{% url \\'dashboard\\' %}",
        "{% url 'dashboard' %}"
    ),
    # Fix 2: mark-balance-paid data-url
    (
        "{% url \\'mark-balance-paid\\' rec.id %}",
        "{% url 'mark-balance-paid' rec.id %}"
    ),
]

applied = 0
for bad, good in fixes:
    if bad in raw:
        raw = raw.replace(bad, good)
        applied += 1
        print(f'Fixed: {bad[:50]}...')
    elif good in raw:
        print(f'Already OK: {good[:50]}...')
    else:
        print(f'NOT FOUND: {bad[:50]}', file=sys.stderr)

with open(path, 'w', encoding='utf-8') as f:
    f.write(raw)

print(f'\n{applied} fix(es) applied. Done.')

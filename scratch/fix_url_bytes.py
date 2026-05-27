path = 'templates/core/outstanding_balances.html'

with open(path, 'rb') as f:
    raw = f.read()

# The file contains literal backslash-quote: b"\\'"  (two bytes: 0x5C 0x27)
# Django template engine needs just: b"'"  (one byte: 0x27)
# Only fix inside {% url ... %} blocks — replace  \' with ' within those blocks

import re

def fix_url_tags(content: bytes) -> bytes:
    def replacer(m):
        # Replace backslash-quote inside this tag only
        return m.group(0).replace(b"\\'", b"'")
    return re.sub(rb'\{%-?\s*url\b[^%]*%\}', replacer, content)

fixed = fix_url_tags(raw)

changed = fixed != raw
with open(path, 'wb') as f:
    f.write(fixed)

if changed:
    print('URL tags fixed — backslash-quotes removed inside {% url %} blocks.')
else:
    print('No changes needed.')

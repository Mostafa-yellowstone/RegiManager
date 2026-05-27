import sys

path = 'templates/core/outstanding_balances.html'

with open(path, encoding='utf-8') as f:
    content = f.read()

changes = 0

# ── Fix 1: button onclick → data-attributes ──────────────────────────────
OLD1 = (
    '                    <!-- Mark paid button -->\n'
    '                    <td>\n'
    '                        <button class="pay-btn"\n'
    '                                id="btn-{{ rec.id }}"\n'
    "                                onclick=\"markPaid({{ rec.id }}, '{{ rec.receipt_number }}')\">\n"
    '                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>\n'
    '                            Mark Paid\n'
    '                        </button>\n'
    '                    </td>'
)
NEW1 = (
    '                    <!-- Mark paid button -->\n'
    '                    <td>\n'
    '                        <button class="pay-btn"\n'
    '                                id="btn-{{ rec.id }}"\n'
    '                                data-id="{{ rec.id }}"\n'
    '                                data-receipt="{{ rec.receipt_number }}"\n'
    "                                data-url=\"{% url 'mark-balance-paid' rec.id %}\"\n"
    '                                onclick="markPaid(this)">\n'
    '                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>\n'
    '                            Mark Paid\n'
    '                        </button>\n'
    '                    </td>'
)
if OLD1 in content:
    content = content.replace(OLD1, NEW1, 1)
    changes += 1
    print('Fix 1 (button data-attrs): OK')
else:
    print('Fix 1 (button data-attrs): NOT FOUND', file=sys.stderr)

# ── Fix 2: add id="modalCancelBtn" to cancel button ──────────────────────
OLD2 = '            <button class="ob-modal-cancel" onclick="closePayModal()">Cancel</button>'
NEW2 = '            <button class="ob-modal-cancel" id="modalCancelBtn" onclick="closePayModal()">Cancel</button>'
if OLD2 in content:
    content = content.replace(OLD2, NEW2, 1)
    changes += 1
    print('Fix 2 (cancel btn id): OK')
else:
    print('Fix 2 (cancel btn id): NOT FOUND', file=sys.stderr)

# ── Fix 3: insert error modal block right before <script> ────────────────
ERROR_MODAL = (
    '\n<!-- Error Modal -->\n'
    '<div class="ob-overlay" id="payErrorOverlay">\n'
    '    <div class="ob-modal">\n'
    '        <div class="ob-modal-icon" style="background: linear-gradient(135deg,#fee2e2,#fecaca);">\n'
    '            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="#dc2626" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>\n'
    '        </div>\n'
    '        <h2 id="errorTitle" style="color:#b91c1c;">Payment Failed</h2>\n'
    '        <p id="errorDesc" style="color:#64748b;">Something went wrong. No data was changed.</p>\n'
    '        <div class="ob-modal-actions" style="justify-content:center;">\n'
    '            <button class="ob-modal-cancel" style="flex:0 0 auto;padding:.8rem 2.5rem;" onclick="closeErrorModal()">Close</button>\n'
    '        </div>\n'
    '    </div>\n'
    '</div>\n'
)

MARKER = '\n<script>\n/* \u2500'
if MARKER in content:
    content = content.replace(MARKER, ERROR_MODAL + MARKER, 1)
    changes += 1
    print('Fix 3 (error modal): OK')
else:
    print('Fix 3 (error modal): NOT FOUND', file=sys.stderr)
    # Try alternate marker
    MARKER2 = '\n<script>\nconst CSRF'
    if MARKER2 in content:
        content = content.replace(MARKER2, ERROR_MODAL + MARKER2, 1)
        changes += 1
        print('Fix 3b (error modal alt marker): OK')

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f'\n{changes} fix(es) applied.')

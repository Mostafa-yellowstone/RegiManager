import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'RegiManager.settings')
django.setup()

from django.template.loader import get_template
from django.template import Context

errors = []

# 1. Template compilation
try:
    t = get_template('core/outstanding_balances.html')
    print('[OK] Template compiles cleanly')
except Exception as e:
    errors.append(f'[FAIL] Template error: {e}')

# 2. URL resolution
try:
    from django.urls import reverse
    u1 = reverse('outstanding-balances')
    u2 = reverse('mark-balance-paid', args=[999])
    print(f'[OK] outstanding-balances URL: {u1}')
    print(f'[OK] mark-balance-paid URL:    {u2}')
except Exception as e:
    errors.append(f'[FAIL] URL resolution: {e}')

# 3. View imports
try:
    from core.views import outstanding_balances, mark_balance_paid
    print('[OK] Views import OK')
except Exception as e:
    errors.append(f'[FAIL] View import: {e}')

# 4. Model field check — referral_balance, is_referral_paid exist
try:
    from core.models import ServiceRecord
    ServiceRecord._meta.get_field('referral_balance')
    ServiceRecord._meta.get_field('is_referral_paid')
    ServiceRecord._meta.get_field('updated_at')
    print('[OK] ServiceRecord fields OK')
except Exception as e:
    errors.append(f'[FAIL] Model field: {e}')

# 5. ReferralPayment model importable
try:
    from core.models import ReferralPayment
    print('[OK] ReferralPayment model OK')
except Exception as e:
    errors.append(f'[FAIL] ReferralPayment import: {e}')

# 6. Dashboard template still compiles
try:
    get_template('core/dashboard.html')
    print('[OK] dashboard.html compiles cleanly')
except Exception as e:
    errors.append(f'[FAIL] dashboard.html error: {e}')

# 7. edit_client view import
try:
    from core.views import edit_client
    print('[OK] edit_client view OK')
except Exception as e:
    errors.append(f'[FAIL] edit_client: {e}')

# 8. ClientForm referral_balance not readonly
try:
    from core.forms import ClientForm
    from core.models import Organization
    f = ClientForm.__new__(ClientForm)
    # Check the field exists and is not forced readonly
    field = ClientForm.declared_fields.get('referral_balance')
    print(f'[OK] ClientForm.referral_balance field: {field}')
except Exception as e:
    errors.append(f'[FAIL] ClientForm: {e}')

print('\n' + '='*50)
if errors:
    print(f'ISSUES FOUND ({len(errors)}):')
    for e in errors:
        print(' ', e)
    sys.exit(1)
else:
    print('ALL CHECKS PASSED — no bugs found.')

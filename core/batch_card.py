"""Yellow NY DMV batch-number card (MV-107) filled from the dashboard."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from .access import organizations_for_user


def batch_card_slots(card_date, terminal=""):
    """Digit boxes for the landscape batch card.

    Left to right: last digit of the year, month, day, then the two-digit
    period of the year (20 for the 2020s) which sits between the printed X
    boxes, then up to three terminal digits.
    """
    year = card_date.year
    digits = "".join(ch for ch in (terminal or "") if ch.isdigit())[:3]
    return {
        "year": str(year % 10),
        "month": f"{card_date.month:02d}",
        "day": f"{card_date.day:02d}",
        "period": f"{year // 100:02d}",
        "terminal": f"{digits:<3}",
    }


@login_required
def batch_number_card(request):
    if request.user.is_superuser:
        return redirect("/admin/")

    organizations = organizations_for_user(request)
    if not organizations.exists():
        messages.error(request, "Your account is currently disabled for all psbs. Contact an owner.")
        return redirect("dashboard")

    orgs = list(organizations.order_by("name"))
    selected_id = request.GET.get("organization")
    organization = None
    if selected_id and str(selected_id).isdigit():
        organization = next((org for org in orgs if org.id == int(selected_id)), None)
    if organization is None:
        organization = orgs[0]

    return render(
        request,
        "core/batch_number_card.html",
        {
            "organizations": orgs,
            "organization": organization,
            "today": timezone.localdate().isoformat(),
        },
    )

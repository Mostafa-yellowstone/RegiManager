"""Time window and Excel export for an agent's service audit."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from urllib.parse import urlencode

from django.db.models import Count, Q, Sum
from django.utils import timezone

from .models import ServiceRecord
from .text_search import apply_text_search

AUDIT_PERIODS = (
    ("today", "Today"),
    ("week", "Week"),
    ("month", "Month"),
    ("quarter", "Quarter"),
    ("year", "Year"),
    ("all", "All time"),
    ("custom", "Custom"),
)
AUDIT_PERIOD_KEYS = {key for key, _label in AUDIT_PERIODS}


def _shift_month(today: date, offset: int) -> tuple[int, int]:
    total = today.year * 12 + (today.month - 1) + offset
    return total // 12, (total % 12) + 1


def _parse_date(raw: str) -> date | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        return timezone.datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def resolve_audit_window(params, *, today: date | None = None) -> dict:
    """Inclusive window for the audit CRM. ``params`` is a GET-like mapping."""
    today = today or timezone.localdate()
    period = (params.get("period") or "month").strip().lower()
    if period == "day":
        period = "today"
    if period not in AUDIT_PERIOD_KEYS:
        period = "month"
    try:
        offset = int(params.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0
    offset = max(-120, min(offset, 24))

    start = end = None
    if period == "today":
        day = today + timedelta(days=offset)
        start = end = day
        if offset == 0:
            label = f"Today · {day.strftime('%b %d, %Y')}"
        elif offset == -1:
            label = f"Yesterday · {day.strftime('%b %d, %Y')}"
        else:
            label = day.strftime("%A, %b %d, %Y")
    elif period == "week":
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        end = start + timedelta(days=6)
        label = f"{start.strftime('%b %d')} – {end.strftime('%b %d, %Y')}"
    elif period == "quarter":
        quarter_index = today.year * 4 + ((today.month - 1) // 3) + offset
        year, quarter = divmod(quarter_index, 4)
        start_month = quarter * 3 + 1
        start = date(year, start_month, 1)
        end_month = start_month + 2
        end = date(year, end_month, calendar.monthrange(year, end_month)[1])
        label = f"Q{quarter + 1} {year}"
    elif period == "year":
        year = today.year + offset
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        label = str(year)
    elif period == "all":
        label = "All time"
        offset = 0
    elif period == "custom":
        start = _parse_date(params.get("start_date"))
        end = _parse_date(params.get("end_date"))
        if start and end and end < start:
            start, end = end, start
        if start and not end:
            end = start
        if end and not start:
            start = end
        if start and end:
            label = f"{start.strftime('%b %d, %Y')} – {end.strftime('%b %d, %Y')}"
        else:
            label = "Custom range"
        offset = 0
    else:
        period = "month"
        year, month = _shift_month(today, offset)
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        label = start.strftime("%B %Y")

    status = (params.get("status") or "").strip().lower()
    if status not in {key for key, _label in ServiceRecord.STATUS_CHOICES}:
        status = ""

    service_type = (params.get("service_type") or "").strip()
    payment_method = (params.get("payment_method") or "").strip().lower()
    if payment_method not in {key for key, _label in ServiceRecord.PAYMENT_METHODS}:
        payment_method = ""

    min_fee_raw = (params.get("min_fee") or "").strip()
    max_fee_raw = (params.get("max_fee") or "").strip()
    min_fee = None
    max_fee = None
    if min_fee_raw:
        try:
            min_fee = Decimal(min_fee_raw)
        except Exception:
            min_fee = None
    if max_fee_raw:
        try:
            max_fee = Decimal(max_fee_raw)
        except Exception:
            max_fee = None

    has_notes = (params.get("has_notes") or "").strip().lower()
    if has_notes not in {"yes", "no"}:
        has_notes = ""

    sort_by = (params.get("sort") or "-transaction_date").strip()
    allowed_sorts = {
        "-transaction_date", "transaction_date",
        "-service_fee", "service_fee",
        "-created_at", "created_at",
        "client_name", "-client_name",
        "receipt_number", "-receipt_number",
        "status", "-status",
    }
    if sort_by not in allowed_sorts:
        sort_by = "-transaction_date"

    return {
        "period": period,
        "offset": offset,
        "start": start,
        "end": end,
        "label": label,
        "start_date": start.isoformat() if start else "",
        "end_date": end.isoformat() if end else "",
        "q": (params.get("q") or "").strip(),
        "status": status,
        "service_type": service_type,
        "payment_method": payment_method,
        "min_fee": str(min_fee) if min_fee is not None else "",
        "max_fee": str(max_fee) if max_fee is not None else "",
        "has_notes": has_notes,
        "sort": sort_by,
        "can_step": period not in {"all", "custom"},
    }


def audit_query(window: dict, **extra) -> str:
    params = {
        "period": window.get("period"),
        "offset": window.get("offset"),
        "q": window.get("q"),
        "status": window.get("status"),
        "service_type": window.get("service_type"),
        "payment_method": window.get("payment_method"),
        "min_fee": window.get("min_fee"),
        "max_fee": window.get("max_fee"),
        "has_notes": window.get("has_notes"),
        "sort": window.get("sort"),
    }
    if window.get("period") == "custom":
        params["start_date"] = window.get("start_date")
        params["end_date"] = window.get("end_date")
    params.update(extra)
    return urlencode({key: value for key, value in params.items() if value not in (None, "")})


def build_active_audit_chips(window: dict, *, avail_service_types=None, payment_methods=None, tab="audit", activity_date="") -> list[dict]:
    """Builds chic, dismissible tag pills for every active filter."""
    chips = []
    base_extra = {}
    if tab:
        base_extra["tab"] = tab
    if activity_date:
        base_extra["activity_date"] = activity_date

    service_map = dict(avail_service_types or [])
    payment_map = dict(payment_methods or ServiceRecord.PAYMENT_METHODS)
    status_map = dict(ServiceRecord.STATUS_CHOICES)

    if window.get("q"):
        remove_href = f"?{audit_query(window, q='', **base_extra)}"
        chips.append({
            "key": "q",
            "label": f'Search: "{window["q"]}"',
            "remove_href": remove_href,
        })

    if window.get("status"):
        st_label = status_map.get(window["status"], window["status"].title())
        remove_href = f"?{audit_query(window, status='', **base_extra)}"
        chips.append({
            "key": "status",
            "label": f"Status: {st_label}",
            "remove_href": remove_href,
        })

    if window.get("service_type"):
        srv_label = service_map.get(window["service_type"], window["service_type"])
        remove_href = f"?{audit_query(window, service_type='', **base_extra)}"
        chips.append({
            "key": "service_type",
            "label": f"Service: {srv_label}",
            "remove_href": remove_href,
        })

    if window.get("payment_method"):
        pm_label = payment_map.get(window["payment_method"], window["payment_method"].title())
        remove_href = f"?{audit_query(window, payment_method='', **base_extra)}"
        chips.append({
            "key": "payment_method",
            "label": f"Payment: {pm_label}",
            "remove_href": remove_href,
        })

    if window.get("min_fee"):
        remove_href = f"?{audit_query(window, min_fee='', **base_extra)}"
        chips.append({
            "key": "min_fee",
            "label": f"Min: ${window['min_fee']}",
            "remove_href": remove_href,
        })

    if window.get("max_fee"):
        remove_href = f"?{audit_query(window, max_fee='', **base_extra)}"
        chips.append({
            "key": "max_fee",
            "label": f"Max: ${window['max_fee']}",
            "remove_href": remove_href,
        })

    if window.get("has_notes") == "yes":
        remove_href = f"?{audit_query(window, has_notes='', **base_extra)}"
        chips.append({
            "key": "has_notes",
            "label": "Has Notes",
            "remove_href": remove_href,
        })
    elif window.get("has_notes") == "no":
        remove_href = f"?{audit_query(window, has_notes='', **base_extra)}"
        chips.append({
            "key": "has_notes",
            "label": "No Notes",
            "remove_href": remove_href,
        })

    sort = window.get("sort") or "-transaction_date"
    if sort != "-transaction_date":
        sort_labels = {
            "transaction_date": "Oldest Date First",
            "-service_fee": "Highest Fee First",
            "service_fee": "Lowest Fee First",
            "client_name": "Client Name (A–Z)",
            "-created_at": "Entry Time (Latest)",
        }
        remove_href = f"?{audit_query(window, sort='-transaction_date', **base_extra)}"
        chips.append({
            "key": "sort",
            "label": f"Sort: {sort_labels.get(sort, sort)}",
            "remove_href": remove_href,
        })

    return chips


def filter_and_sort_team(agent_data: list[dict], *, role: str = "", activity: str = "", sort: str = "-revenue") -> list[dict]:
    """Filters and sorts team members in the Agent Auditing directory."""
    results = list(agent_data)
    
    role = (role or "").strip().lower()
    if role:
        results = [d for d in results if getattr(d.get("membership"), "role", "").lower() == role]

    activity = (activity or "").strip().lower()
    if activity == "active":
        results = [d for d in results if d.get("total_records", 0) > 0]
    elif activity == "has_errors":
        results = [d for d in results if d.get("failed", 0) > 0]
    elif activity == "inactive":
        results = [d for d in results if d.get("total_records", 0) == 0]

    sort = (sort or "-revenue").strip()
    if sort == "-revenue":
        results.sort(key=lambda d: (d.get("total_revenue") or Decimal("0")), reverse=True)
    elif sort == "revenue":
        results.sort(key=lambda d: (d.get("total_revenue") or Decimal("0")))
    elif sort == "-records":
        results.sort(key=lambda d: d.get("total_records", 0), reverse=True)
    elif sort == "records":
        results.sort(key=lambda d: d.get("total_records", 0))
    elif sort == "-failed":
        results.sort(key=lambda d: d.get("failed", 0), reverse=True)
    elif sort == "name":
        results.sort(key=lambda d: d.get("name", "").lower())
    elif sort == "-name":
        results.sort(key=lambda d: d.get("name", "").lower(), reverse=True)

    return results


def filter_agent_services(qs, window: dict):
    if window.get("start") and window.get("end"):
        qs = qs.filter(transaction_date__gte=window["start"], transaction_date__lte=window["end"])
    if window.get("status"):
        qs = qs.filter(status=window["status"])
    if window.get("service_type"):
        qs = qs.filter(service_type=window["service_type"])
    if window.get("payment_method"):
        qs = qs.filter(Q(payment_method=window["payment_method"]) | Q(payment_method_2=window["payment_method"]))
    if window.get("min_fee"):
        try:
            qs = qs.filter(service_fee__gte=Decimal(window["min_fee"]))
        except Exception:
            pass
    if window.get("max_fee"):
        try:
            qs = qs.filter(service_fee__lte=Decimal(window["max_fee"]))
        except Exception:
            pass
    if window.get("has_notes") == "yes":
        qs = qs.exclude(notes="")
    elif window.get("has_notes") == "no":
        qs = qs.filter(Q(notes="") | Q(notes__isnull=True))
    if window.get("q"):
        qs = apply_text_search(
            qs,
            window["q"],
            ["receipt_number", "client_name", "plate_number", "vin", "phone_no", "case_id", "notes"],
        )
    return qs


def audit_totals(qs) -> dict:
    row = qs.aggregate(
        total=Count("id"),
        fees=Sum("service_fee"),
        profit=Sum("processing_fee"),
        failed=Count("id", filter=Q(status="failed")),
        refunds=Count("id", filter=Q(status="refund")),
        completed=Count("id", filter=Q(status="completed")),
    )
    total = row["total"] or 0
    failed = row["failed"] or 0
    worked = total - (row["refunds"] or 0)
    return {
        "total": total,
        "fees": row["fees"] or Decimal("0"),
        "profit": row["profit"] or Decimal("0"),
        "failed": failed,
        "refunds": row["refunds"] or 0,
        "completed": row["completed"] or 0,
        "error_rate": round((failed / worked * 100), 1) if worked else 0,
    }


def service_breakdown(qs, organization) -> list[dict]:
    from .models import CustomServiceType

    labels = dict(ServiceRecord.SERVICE_TYPES)
    labels.update(
        CustomServiceType.objects.filter(organization=organization).values_list("key", "label")
    )
    rows = (
        qs.values("service_type")
        .annotate(count=Count("id"), fees=Sum("service_fee"))
        .order_by("-count", "service_type")[:8]
    )
    return [
        {
            "label": labels.get(row["service_type"], row["service_type"] or "Service"),
            "count": row["count"],
            "fees": row["fees"] or Decimal("0"),
        }
        for row in rows
    ]


def _service_labels(records) -> dict:
    from .models import CustomServiceType

    labels = dict(ServiceRecord.SERVICE_TYPES)
    org_ids = {record.organization_id for record in records}
    if org_ids:
        labels.update(
            CustomServiceType.objects.filter(organization_id__in=org_ids).values_list("key", "label")
        )
    return labels


def audit_workbook(records, *, agent_name: str, window: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    labels = _service_labels(records)
    book = Workbook()
    sheet = book.active
    sheet.title = "Service audit"
    headers = [
        "Receipt date",
        "Entered",
        "Receipt",
        "Client",
        "Phone",
        "Plate",
        "VIN",
        "Service",
        "Status",
        "Payment",
        "Service fee",
        "DMV fee",
        "Processing fee",
        "Notes",
    ]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.append([f"{agent_name} · {window['label']}"])
    for record in records:
        entered = timezone.localtime(record.created_at).strftime("%Y-%m-%d %H:%M")
        sheet.append([
            record.transaction_date.isoformat() if record.transaction_date else "",
            entered,
            record.receipt_number or "",
            record.client_name or "",
            record.phone_no or "",
            record.plate_number or "",
            record.vin or "",
            labels.get(record.service_type, record.service_type or ""),
            record.get_status_display(),
            record.get_payment_method_display() or "",
            float(record.service_fee or 0),
            float(record.dmv_fee or 0),
            float(record.processing_fee or 0),
            record.notes or "",
        ])
    for column in sheet.columns:
        letter = column[0].column_letter
        width = max(12, min(36, max(len(str(cell.value or "")) for cell in column[:40]) + 2))
        sheet.column_dimensions[letter].width = width
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()

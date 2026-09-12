"""Serializers / payload builders for the client mobile wallet API."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .insurance_policy_schedule import summarize_insurance_schedule
from .models import (
    Client,
    DailyPaymentTransaction,
    InsurancePolicy,
    InsurancePolicyDocument,
    InsurancePolicyVehicle,
    ServiceDocument,
    ServiceRecord,
    Vehicle,
)


def _money(value) -> str:
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except Exception:
        amount = Decimal("0.00")
    return f"{amount:.2f}"


def client_profile_payload(client: Client) -> dict:
    return {
        "id": client.id,
        "full_name": client.full_display_name or client.name,
        "first_name": client.first_name,
        "last_name": client.last_name,
        "phone_number": client.phone_number or "",
        "email": client.email or "",
        "driver_license": client.driver_license or "",
        "dob": client.dob.isoformat() if client.dob else None,
        "is_commercial": bool(client.is_commercial),
        "business_name": client.business_name or "",
        "organization_id": client.organization_id,
        "address": client.full_address or "",
    }


def schedule_payload(policy: InsurancePolicy) -> dict:
    summary = summarize_insurance_schedule(policy)
    remaining_amount = sum((r.total_due for r in summary["installments"] if not r.is_paid), Decimal("0.00"))
    paid_amount = sum((r.total_due for r in summary["installments"] if r.is_paid), Decimal("0.00"))
    installments = []
    for row in summary["installments"]:
        installments.append(
            {
                "id": row.id,
                "number": row.display_number,
                "installment_number": row.installment_number,
                "due_date": row.due_date.isoformat() if row.due_date else None,
                "amount": _money(row.amount),
                "installment_fee": _money(row.installment_fee),
                "total_due": _money(row.total_due),
                "is_paid": bool(row.is_paid),
                "is_deposit": bool(row.is_deposit),
            }
        )
    next_row = summary.get("next_due")
    return {
        "total": summary["total"],
        "paid": summary["paid"],
        "remaining": summary["open"],
        "paid_amount": _money(paid_amount),
        "remaining_amount": _money(remaining_amount),
        "next_due_date": summary["next_due_date"].isoformat() if summary.get("next_due_date") else None,
        "next_due_amount": _money(summary["next_due_amount"]) if summary.get("next_due_amount") is not None else None,
        "next_installment_id": next_row.id if next_row else None,
        "installments": installments,
    }


def policy_list_item(policy: InsurancePolicy) -> dict:
    company = policy.insurance_company.name if policy.insurance_company_id else ""
    summary = summarize_insurance_schedule(policy)
    remaining_amount = sum((r.total_due for r in summary["installments"] if not r.is_paid), Decimal("0.00"))
    return {
        "id": policy.id,
        "policy_number": policy.policy_number,
        "status": policy.status,
        "status_display": policy.get_status_display(),
        "stage": policy.stage,
        "stage_display": policy.get_stage_display() if hasattr(policy, "get_stage_display") else policy.stage,
        "insurance_type": policy.insurance_type or "",
        "insurance_type_display": (
            policy.get_insurance_type_display() if policy.insurance_type else ""
        ),
        "company": company,
        "named_insured": policy.named_insured or "",
        "start_date": policy.start_date.isoformat() if policy.start_date else None,
        "end_date": policy.end_date.isoformat() if getattr(policy, "end_date", None) else None,
        "renewal_date": policy.renewal_date.isoformat() if getattr(policy, "renewal_date", None) else None,
        "next_due_date": summary["next_due_date"].isoformat() if summary.get("next_due_date") else None,
        "next_due_amount": _money(summary["next_due_amount"]) if summary.get("next_due_amount") is not None else None,
        "remaining_payments": summary["open"],
        "remaining_amount": _money(remaining_amount),
    }


def policy_detail_payload(policy: InsurancePolicy) -> dict:
    data = policy_list_item(policy)
    data["schedule"] = schedule_payload(policy)
    data["vin"] = getattr(policy, "vin", "") or ""
    data["plate_number"] = getattr(policy, "plate_number", "") or ""
    return data


def insurance_document_payload(doc: InsurancePolicyDocument, *, request=None) -> dict:
    file_url = None
    if doc.file and request:
        try:
            file_url = request.build_absolute_uri(
                f"/api/client/documents/insurance/{doc.id}/file/"
            )
        except Exception:
            file_url = None
    return {
        "id": doc.id,
        "kind": "insurance",
        "document_type": doc.document_type,
        "document_type_display": doc.get_document_type_display(),
        "title": doc.title,
        "policy_id": doc.policy_id,
        "policy_number": doc.policy.policy_number if doc.policy_id else "",
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "file_url": file_url,
        "has_file": bool(doc.file),
    }


def dmv_document_payload(doc: ServiceDocument, *, request=None) -> dict:
    file_url = None
    if doc.file and request:
        try:
            file_url = request.build_absolute_uri(
                f"/api/client/documents/dmv/{doc.id}/file/"
            )
        except Exception:
            file_url = None
    vehicle_label = ""
    if getattr(doc, "vehicle", None):
        vehicle_label = f"{doc.vehicle.year or ''} {doc.vehicle.make or ''} {doc.vehicle.model or ''}".strip()
    return {
        "id": doc.id,
        "kind": "dmv",
        "document_type": doc.document_type,
        "document_type_display": doc.get_document_type_display(),
        "title": getattr(doc, "custom_name", "") or doc.get_document_type_display(),
        "vehicle_label": vehicle_label,
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "file_url": file_url,
        "has_file": bool(doc.file),
    }


def payment_payload(tx: DailyPaymentTransaction) -> dict:
    return {
        "id": tx.id,
        "kind": "insurance_payment",
        "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
        "amount": _money(tx.amount),
        "payment_type": tx.payment_type,
        "payment_type_display": tx.get_payment_type_display(),
        "payment_method": tx.payment_method,
        "payment_method_display": tx.get_payment_method_display(),
        "policy_number": tx.policy_number or (
            tx.insurance_policy.policy_number if tx.insurance_policy_id else ""
        ),
        "policy_id": tx.insurance_policy_id,
        "company": tx.insurance_company.name if tx.insurance_company_id else "",
        "coverage": tx.coverage or "",
        "next_payment_due": tx.next_payment_due.isoformat() if tx.next_payment_due else None,
        "next_payment_amount": _money(tx.next_payment_amount) if tx.next_payment_amount is not None else None,
        "remaining_amount": _money(tx.remaining_amount) if tx.remaining_amount is not None else None,
        "remaining_payments": tx.remaining_payments,
        "section_2119": _money(tx.section_2119) if tx.section_2119 is not None else None,
        "broker_fee": _money(tx.broker_fee) if getattr(tx, "broker_fee", None) is not None else None,
        "credit_card_fee": _money(tx.credit_card_fee) if tx.credit_card_fee is not None else None,
        "notes": (tx.notes or "")[:200],
    }


def vehicle_payload(vehicle: Vehicle) -> dict:
    return {
        "id": vehicle.id,
        "source": "fleet",
        "year": vehicle.year,
        "make": vehicle.make or "",
        "model": vehicle.model or "",
        "vin": vehicle.vin or "",
        "plate_number": vehicle.plate_number or "",
        "vehicle_type": vehicle.vehicle_type,
        "vehicle_type_display": vehicle.get_vehicle_type_display() if vehicle.vehicle_type else "",
        "body_type": vehicle.body_type or "",
        "insurance_expiration_date": (
            vehicle.insurance_expiration_date.isoformat()
            if getattr(vehicle, "insurance_expiration_date", None)
            else None
        ),
        "label": f"{vehicle.year or ''} {vehicle.make or ''} {vehicle.model or ''}".strip() or vehicle.vin or "Vehicle",
        "policy_id": None,
        "policy_number": "",
    }


def policy_vehicle_payload(row: InsurancePolicyVehicle) -> dict:
    return {
        "id": f"pv-{row.id}",
        "source": "policy",
        "year": row.year,
        "make": row.make or "",
        "model": "",
        "vin": row.vin or "",
        "plate_number": row.plate_number or "",
        "vehicle_type": "",
        "vehicle_type_display": "Policy vehicle",
        "body_type": "",
        "insurance_expiration_date": (
            row.expiration_date.isoformat() if getattr(row, "expiration_date", None) else None
        ),
        "label": f"{row.year or ''} {row.make or ''}".strip() or row.vin or f"Unit #{row.auto_number}",
        "policy_id": row.policy_id,
        "policy_number": row.policy.policy_number if row.policy_id else "",
    }


def service_receipt_payload(record: ServiceRecord) -> dict:
    return {
        "id": f"sr-{record.id}",
        "kind": "service_receipt",
        "receipt_number": getattr(record, "receipt_number", "") or f"SR-{record.id}",
        "title": record.service_type or record.transaction_type or "Service",
        "service_type": record.service_type or "",
        "transaction_type": record.transaction_type or "",
        "status": record.status,
        "status_display": record.get_status_display() if hasattr(record, "get_status_display") else record.status,
        "transaction_date": (
            record.transaction_date.isoformat()
            if getattr(record, "transaction_date", None)
            else (record.created_at.date().isoformat() if record.created_at else None)
        ),
        "amount": _money(getattr(record, "service_fee", 0)),
        "service_fee": _money(getattr(record, "service_fee", 0)),
        "plate_number": record.plate_number or "",
        "vin": record.vin or "",
        "vehicle_id": record.vehicle_id,
        "company": "",
        "policy_number": "",
    }


def insurance_receipt_payload(tx: DailyPaymentTransaction) -> dict:
    return {
        "id": f"ip-{tx.id}",
        "kind": "insurance_payment",
        "receipt_number": f"PAY-{tx.id}",
        "title": tx.get_payment_type_display(),
        "service_type": tx.get_payment_type_display(),
        "transaction_type": "Insurance Payment",
        "status": "completed",
        "status_display": "Completed",
        "transaction_date": tx.transaction_date.isoformat() if tx.transaction_date else None,
        "amount": _money(tx.amount),
        "service_fee": _money(tx.amount),
        "plate_number": "",
        "vin": "",
        "vehicle_id": None,
        "company": tx.insurance_company.name if tx.insurance_company_id else "",
        "policy_number": tx.policy_number or (
            tx.insurance_policy.policy_number if tx.insurance_policy_id else ""
        ),
    }


def build_client_vehicles(client: Client) -> list[dict]:
    """Fleet vehicles + vehicles listed on the client's insurance policies."""
    rows = [vehicle_payload(v) for v in Vehicle.objects.filter(client=client).order_by("-id")]
    seen_vins = {(r.get("vin") or "").strip().upper() for r in rows if r.get("vin")}
    seen_plates = {(r.get("plate_number") or "").strip().upper() for r in rows if r.get("plate_number")}
    policy_vehicles = (
        InsurancePolicyVehicle.objects.filter(policy__client=client)
        .select_related("policy")
        .order_by("policy_id", "auto_number")
    )
    for pv in policy_vehicles:
        vin = (pv.vin or "").strip().upper()
        plate = (pv.plate_number or "").strip().upper()
        if vin and vin in seen_vins:
            continue
        if plate and plate in seen_plates:
            continue
        payload = policy_vehicle_payload(pv)
        rows.append(payload)
        if vin:
            seen_vins.add(vin)
        if plate:
            seen_plates.add(plate)
    return rows


def build_client_receipts(client: Client, *, limit: int = 100) -> list[dict]:
    """DMV/service receipts plus insurance daily payment receipts."""
    service_rows = list(
        ServiceRecord.objects.filter(vehicle__client=client)
        .select_related("vehicle")
        .order_by("-transaction_date", "-id")[:limit]
    )
    # Also include orphaned records that snapshotted this client's name when vehicle is missing
    if client.name:
        extra_q = ServiceRecord.objects.filter(
            vehicle__isnull=True,
            organization_id=client.organization_id,
            client_name__iexact=client.name,
        )
        service_ids = {r.id for r in service_rows}
        for r in extra_q.order_by("-transaction_date", "-id")[:50]:
            if r.id not in service_ids:
                service_rows.append(r)
                service_ids.add(r.id)

    payments = list(
        DailyPaymentTransaction.objects.filter(client=client)
        .select_related("insurance_company", "insurance_policy")
        .order_by("-transaction_date", "-id")[:limit]
    )
    combined = [service_receipt_payload(r) for r in service_rows]
    combined.extend(insurance_receipt_payload(p) for p in payments)
    combined.sort(key=lambda row: row.get("transaction_date") or "", reverse=True)
    return combined[:limit]



def build_upcoming_items(client: Client, *, days: int = 90) -> list[dict]:
    today = timezone.localdate()
    horizon = today + timedelta(days=days)
    items: list[dict] = []

    for policy in InsurancePolicy.objects.filter(client=client).select_related("insurance_company"):
        summary = summarize_insurance_schedule(policy)
        due = summary.get("next_due_date")
        if due and today <= due <= horizon:
            items.append(
                {
                    "id": f"inst-{policy.id}-{due.isoformat()}",
                    "kind": "installment",
                    "title": f"Payment due · {policy.policy_number}",
                    "subtitle": policy.insurance_company.name if policy.insurance_company_id else "Insurance",
                    "date": due.isoformat(),
                    "amount": _money(summary.get("next_due_amount")),
                    "policy_id": policy.id,
                }
            )
        end = getattr(policy, "end_date", None) or getattr(policy, "renewal_date", None)
        if end and today <= end <= horizon:
            items.append(
                {
                    "id": f"pol-exp-{policy.id}",
                    "kind": "policy_expiration",
                    "title": f"Policy expires · {policy.policy_number}",
                    "subtitle": policy.insurance_company.name if policy.insurance_company_id else "Insurance",
                    "date": end.isoformat(),
                    "amount": None,
                    "policy_id": policy.id,
                }
            )

    for vehicle in Vehicle.objects.filter(client=client):
        exp = getattr(vehicle, "insurance_expiration_date", None)
        if exp and today <= exp <= horizon:
            items.append(
                {
                    "id": f"veh-ins-{vehicle.id}",
                    "kind": "vehicle_insurance",
                    "title": f"Vehicle insurance expires",
                    "subtitle": f"{vehicle.year or ''} {vehicle.make or ''} {vehicle.plate_number or ''}".strip(),
                    "date": exp.isoformat(),
                    "amount": None,
                    "vehicle_id": vehicle.id,
                }
            )

    items.sort(key=lambda row: row.get("date") or "9999-99-99")
    return items


def build_alerts(client: Client) -> list[dict]:
    """Lightweight client-facing alerts derived from upcoming items (not staff Notification rows)."""
    today = timezone.localdate()
    alerts = []
    for item in build_upcoming_items(client, days=45)[:12]:
        due = date.fromisoformat(item["date"]) if item.get("date") else None
        days_left = (due - today).days if due else None
        level = "warning" if days_left is not None and days_left <= 14 else "info"
        alerts.append(
            {
                "id": item["id"],
                "title": item["title"],
                "message": item.get("subtitle") or "",
                "level": level,
                "date": item.get("date"),
                "kind": item.get("kind"),
                "is_read": False,
                "policy_id": item.get("policy_id"),
                "vehicle_id": item.get("vehicle_id"),
            }
        )
    return alerts

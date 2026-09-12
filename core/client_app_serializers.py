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
        "label": f"{vehicle.year or ''} {vehicle.make or ''} {vehicle.model or ''}".strip() or vehicle.vin,
    }


def service_receipt_payload(record: ServiceRecord) -> dict:
    return {
        "id": record.id,
        "kind": "service_receipt",
        "receipt_number": getattr(record, "receipt_number", "") or f"SR-{record.id}",
        "service_type": record.service_type or "",
        "transaction_type": record.transaction_type or "",
        "status": record.status,
        "status_display": record.get_status_display() if hasattr(record, "get_status_display") else record.status,
        "transaction_date": (
            record.transaction_date.isoformat()
            if getattr(record, "transaction_date", None)
            else (record.created_at.date().isoformat() if record.created_at else None)
        ),
        "service_fee": _money(getattr(record, "service_fee", 0)),
        "plate_number": record.plate_number or "",
        "vin": record.vin or "",
        "vehicle_id": record.vehicle_id,
    }


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

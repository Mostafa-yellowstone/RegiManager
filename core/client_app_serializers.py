"""Serializers / payload builders for the client mobile wallet API."""

from __future__ import annotations

from decimal import Decimal

from .insurance_policy_schedule import summarize_insurance_schedule
from .models import (
    Client,
    InsurancePolicy,
    InsurancePolicyDocument,
    ServiceDocument,
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
    }


def schedule_payload(policy: InsurancePolicy) -> dict:
    summary = summarize_insurance_schedule(policy)
    remaining_amount = sum((r.total_due for r in summary["installments"] if not r.is_paid), Decimal("0.00"))
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
        "remaining_amount": _money(remaining_amount),
        "next_due_date": summary["next_due_date"].isoformat() if summary.get("next_due_date") else None,
        "next_due_amount": _money(summary["next_due_amount"]) if summary.get("next_due_amount") is not None else None,
        "next_installment_id": next_row.id if next_row else None,
        "installments": installments,
    }


def policy_list_item(policy: InsurancePolicy) -> dict:
    company = policy.insurance_company.name if policy.insurance_company_id else ""
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
    return {
        "id": doc.id,
        "kind": "dmv",
        "document_type": doc.document_type,
        "document_type_display": doc.get_document_type_display(),
        "title": getattr(doc, "custom_name", "") or doc.get_document_type_display(),
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "file_url": file_url,
        "has_file": bool(doc.file),
    }

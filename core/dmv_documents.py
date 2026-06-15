"""
NYS DMV / PSB document catalog for vehicle workflows.
Forms with ``prefill=True`` have PDF templates wired in ``generate_dmv_form``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DmvDocument:
    slug: str
    code: str
    name: str
    description: str
    category: str
    prefill: bool = False
    upload_type: str | None = None
    dmv_url: str = ""
    tags: tuple[str, ...] = ()


DMV_DOCUMENT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("registration", "Registration & Plates"),
    ("title", "Title & Transfer"),
    ("tax", "Sales & Use Tax"),
    ("dealer", "Dealer & Temporary"),
    ("identity", "Identity & Insurance"),
    ("supporting", "Supporting Records"),
)

DMV_NYS_FORMS_BASE = "https://dmv.ny.gov/forms"
DMV_TAX_FORMS_BASE = "https://www.tax.ny.gov/pdf/current_dtf"

DMV_DOCUMENTS: tuple[DmvDocument, ...] = (
    # Registration & Plates
    DmvDocument(
        slug="mv82",
        code="MV-82",
        name="Vehicle Registration / Title Application",
        description="Primary NYS application for new registration, renewal, transfer, or plate changes.",
        category="registration",
        prefill=True,
        upload_type="mv82",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv82.pdf",
        tags=("registration", "title", "plates", "renewal"),
    ),
    DmvDocument(
        slug="mv82b",
        code="MV-82B",
        name="Boat Registration Application",
        description="Application to register or transfer a boat trailer and marine vessel.",
        category="registration",
        prefill=True,
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv82b.pdf",
        tags=("boat", "marine", "trailer"),
    ),
    DmvDocument(
        slug="mv83",
        code="MV-83",
        name="Address Change",
        description="Update mailing or residence address on a registration record.",
        category="registration",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv83.pdf",
        tags=("address", "change"),
    ),
    DmvDocument(
        slug="mv3",
        code="MV-3",
        name="In-Transit Permit / Temporary Registration",
        description="Short-term movement permit before permanent registration is issued.",
        category="registration",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv3.pdf",
        tags=("temporary", "in-transit"),
    ),
    DmvDocument(
        slug="mv44",
        code="MV-44",
        name="Duplicate Registration / Plate Documents",
        description="Request replacement registration documents or plates.",
        category="registration",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv44.pdf",
        tags=("duplicate", "replacement"),
    ),
    # Title & Transfer
    DmvDocument(
        slug="mv900",
        code="MV-900",
        name="Application for Title Only",
        description="Title-only application when registration is handled separately.",
        category="title",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv900.pdf",
        tags=("title", "transfer"),
    ),
    DmvDocument(
        slug="mv103",
        code="MV-103",
        name="Odometer & Damage Disclosure",
        description="Federal odometer statement and damage disclosure for title transfers.",
        category="title",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv103.pdf",
        tags=("odometer", "disclosure", "transfer"),
    ),
    DmvDocument(
        slug="mv104",
        code="MV-104",
        name="Owner's Statement (Unavailable Title)",
        description="Affidavit when the prior title is lost, unavailable, or not produced.",
        category="title",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv104.pdf",
        tags=("affidavit", "lost title"),
    ),
    DmvDocument(
        slug="mv907",
        code="MV-907",
        name="Affidavit of Sale / Transfer",
        description="Seller affidavit supporting ownership transfer and chain of title.",
        category="title",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv907.pdf",
        tags=("sale", "transfer", "affidavit"),
    ),
    DmvDocument(
        slug="mv63",
        code="MV-63",
        name="Power of Attorney",
        description="Authorize a PSB or agent to sign DMV documents on the owner's behalf.",
        category="title",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv63.pdf",
        tags=("poa", "power of attorney"),
    ),
    DmvDocument(
        slug="mv903",
        code="MV-903",
        name="Notice of Lien",
        description="Record or release a lienholder on a vehicle title.",
        category="title",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv903.pdf",
        tags=("lien", "finance"),
    ),
    # Sales & Use Tax
    DmvDocument(
        slug="dtf802",
        code="DTF-802",
        name="Sales Tax Paid on Motor Vehicle",
        description="Report sales tax collected or paid at purchase for DMV processing.",
        category="tax",
        prefill=True,
        upload_type="dtf802",
        dmv_url=f"{DMV_TAX_FORMS_BASE}/dtf802.pdf",
        tags=("sales tax", "purchase"),
    ),
    DmvDocument(
        slug="dtf803",
        code="DTF-803",
        name="Sales Tax Exemption / Credit",
        description="Claim exemption, credit, or out-of-state tax paid on a vehicle purchase.",
        category="tax",
        prefill=True,
        dmv_url=f"{DMV_TAX_FORMS_BASE}/dtf803.pdf",
        tags=("exemption", "credit", "out of state"),
    ),
    DmvDocument(
        slug="dtf804",
        code="DTF-804",
        name="Claim for Sales Tax Refund",
        description="Request a refund when tax was overpaid or paid in error.",
        category="tax",
        dmv_url=f"{DMV_TAX_FORMS_BASE}/dtf804.pdf",
        tags=("refund",),
    ),
    DmvDocument(
        slug="dtf806",
        code="DTF-806",
        name="Report of Sale (Dealer)",
        description="Dealer report of retail sale for sales tax and DMV records.",
        category="tax",
        dmv_url=f"{DMV_TAX_FORMS_BASE}/dtf806.pdf",
        tags=("dealer", "sale report"),
    ),
    # Dealer & Temporary
    DmvDocument(
        slug="mv50",
        code="MV-50",
        name="Dealer's In-Transit / Temporary",
        description="Dealer movement or temporary evidence before permanent registration.",
        category="dealer",
        upload_type="mv50",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv50.pdf",
        tags=("dealer", "temporary"),
    ),
    DmvDocument(
        slug="mv51",
        code="MV-51",
        name="Application for Temporary Registration",
        description="Issue temporary registration while full paperwork is completed.",
        category="dealer",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv51.pdf",
        tags=("temporary", "dealer"),
    ),
    DmvDocument(
        slug="mv52",
        code="MV-52",
        name="Dealer Plate Application",
        description="Apply for or manage dealer demonstration / transporter plates.",
        category="dealer",
        dmv_url=f"{DMV_NYS_FORMS_BASE}/mv52.pdf",
        tags=("dealer plates",),
    ),
    # Identity & Insurance
    DmvDocument(
        slug="driver_license",
        code="NYS ID",
        name="Driver License / Non-Driver ID",
        description="Government photo ID for the registrant or co-registrant.",
        category="identity",
        upload_type="driver_license",
        tags=("id", "license"),
    ),
    DmvDocument(
        slug="insurance_id",
        code="FS-20",
        name="Insurance Identification Card",
        description="Proof of active liability insurance meeting NYS minimums.",
        category="identity",
        upload_type="insurance_id",
        tags=("insurance", "fs-20"),
    ),
    # Supporting Records
    DmvDocument(
        slug="title",
        code="TITLE",
        name="Certificate of Title",
        description="Prior title, out-of-state title, or duplicate title documentation.",
        category="supporting",
        upload_type="title",
        tags=("title certificate",),
    ),
    DmvDocument(
        slug="bill_of_sale",
        code="BOS",
        name="Bill of Sale",
        description="Purchase agreement showing buyer, seller, date, and sale price.",
        category="supporting",
        upload_type="bill_of_sale",
        tags=("purchase", "sale"),
    ),
    DmvDocument(
        slug="reassignments",
        code="REASSIGN",
        name="Title Reassignment Supplements",
        description="Dealer reassignments, odometer statements, and back-of-title transfers.",
        category="supporting",
        upload_type="reassignments",
        tags=("reassignment", "dealer"),
    ),
)

DMV_PREFILL_FORM_MAP: dict[str, str] = {
    doc.slug: f"static/core/pdf/{doc.slug}_template.pdf"
    for doc in DMV_DOCUMENTS
    if doc.prefill
}

DMV_PREFILL_SLUGS = frozenset(DMV_PREFILL_FORM_MAP.keys())


def _normalize_label(value: str) -> str:
    return "".join(ch for ch in (value or "").lower() if ch.isalnum())


def _document_matches_upload(doc: DmvDocument, upload) -> bool:
    if doc.upload_type and upload.document_type == doc.upload_type:
        return bool(upload.file)
    if upload.document_type == "other" and upload.custom_name:
        token = _normalize_label(doc.code)
        custom = _normalize_label(upload.custom_name)
        if token and token in custom:
            return bool(upload.file)
        name_token = _normalize_label(doc.name.split()[0])
        if name_token and name_token in custom:
            return bool(upload.file)
    return False


def build_vehicle_document_hub(
    *,
    documents,
) -> list[dict[str, Any]]:
    """Group catalog entries with attachment status for the vehicle page."""
    uploads = [doc for doc in documents if doc.file]

    categories: list[dict[str, Any]] = []
    for cat_id, cat_label in DMV_DOCUMENT_CATEGORIES:
        items: list[dict[str, Any]] = []
        for entry in DMV_DOCUMENTS:
            if entry.category != cat_id:
                continue
            attached = next((u for u in uploads if _document_matches_upload(entry, u)), None)
            items.append(
                {
                    "slug": entry.slug,
                    "code": entry.code,
                    "name": entry.name,
                    "description": entry.description,
                    "prefill": entry.prefill,
                    "upload_type": entry.upload_type,
                    "dmv_url": entry.dmv_url,
                    "tags": entry.tags,
                    "is_attached": attached is not None,
                    "attached_url": attached.file.url if attached else "",
                    "attached_label": attached.display_name if attached else "",
                    "search_text": " ".join(
                        filter(
                            None,
                            [entry.code, entry.name, entry.description, *entry.tags],
                        )
                    ).lower(),
                }
            )
        if items:
            categories.append(
                {
                    "id": cat_id,
                    "label": cat_label,
                    "count": len(items),
                    "attached_count": sum(1 for item in items if item["is_attached"]),
                    "items": items,
                }
            )
    return categories

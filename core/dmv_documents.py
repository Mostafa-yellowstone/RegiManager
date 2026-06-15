"""
State-specific DMV / PSB document catalogs for vehicle workflows.
Forms with ``prefill=True`` have PDF templates wired in ``generate_dmv_form`` (NY only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .us_states import STATE_LABEL_BY_CODE, US_STATE_CODES, US_STATES


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
CT_FORMS_BASE = "https://portal.ct.gov/-/media/DMV"
PA_FORMS_BASE = "https://www.pa.gov/content/dam/copapwp-pagov/en/penndot/documents/public/dvspubsforms/b-pa-forms"
NJ_FORMS_BASE = "https://www.nj.gov/mvc/pdf"

STATE_DMV_PORTALS: dict[str, str] = {
    "AL": "https://www.alea.gov/dps/driver-license",
    "AK": "https://dmv.alaska.gov/",
    "AZ": "https://azdot.gov/motor-vehicles",
    "AR": "https://www.dfa.arkansas.gov/driver-services/",
    "CA": "https://www.dmv.ca.gov/portal/vehicle-registration/",
    "CO": "https://dmv.colorado.gov/",
    "CT": "https://portal.ct.gov/dmv/vehicle-services/forms",
    "DE": "https://dmv.de.gov/",
    "FL": "https://www.flhsmv.gov/motor-vehicles-tags-titles/",
    "GA": "https://dds.georgia.gov/",
    "HI": "https://hidot.hawaii.gov/highways/driver-licenses/",
    "ID": "https://itd.idaho.gov/itd-services/dmv/",
    "IL": "https://www.ilsos.gov/departments/vehicles/home.html",
    "IN": "https://www.in.gov/bmv/",
    "IA": "https://iowadot.gov/mvd",
    "KS": "https://www.ksrevenue.gov/dovindex.html",
    "KY": "https://drive.ky.gov/",
    "LA": "https://offices.omv.la.gov/",
    "ME": "https://www.maine.gov/sos/bmv/",
    "MD": "https://mva.maryland.gov/",
    "MA": "https://www.mass.gov/orgs/massachusetts-registry-of-motor-vehicles",
    "MI": "https://www.michigan.gov/sos/vehicle",
    "MN": "https://dps.mn.gov/divisions/dvs",
    "MS": "https://www.dor.ms.gov/motor-vehicle",
    "MO": "https://dor.mo.gov/motor-vehicle/",
    "MT": "https://mvdmt.gov/",
    "NE": "https://dmv.nebraska.gov/",
    "NV": "https://dmv.nv.gov/",
    "NH": "https://www.nh.gov/safety/divisions/dmv/",
    "NJ": "https://www.nj.gov/mvc/business/retail/forms/",
    "NM": "https://www.mvd.newmexico.gov/",
    "NY": DMV_NYS_FORMS_BASE,
    "NC": "https://www.ncdot.gov/dmv/",
    "ND": "https://www.dot.nd.gov/driver/",
    "OH": "https://www.bmv.ohio.gov/",
    "OK": "https://oklahoma.gov/service/popular-services/oklahoma-dps---driver-license.html",
    "OR": "https://www.oregon.gov/odot/dmv/pages/vehicle.aspx",
    "PA": "https://www.pa.gov/agencies/dmv/vehicle-services/motor-vehicle-forms",
    "RI": "https://dmv.ri.gov/",
    "SC": "https://scdmvonline.com/",
    "SD": "https://dps.sd.gov/driver-licensing",
    "TN": "https://www.tn.gov/safety/driver-services.html",
    "TX": "https://www.txdmv.gov/motorists",
    "UT": "https://dmv.utah.gov/",
    "VT": "https://dmv.vermont.gov/",
    "VA": "https://www.dmv.virginia.gov/",
    "WA": "https://dol.wa.gov/vehicles-and-boats",
    "WV": "https://transportation.wv.gov/dmv/",
    "WI": "https://wisconsindot.gov/Pages/dmv/online/default.aspx",
    "WY": "https://www.dot.state.wy.us/home/driver_license_records.html",
}


def normalize_state_code(value: str) -> str:
    raw = (value or "").strip().upper()
    if raw in US_STATE_CODES:
        return raw
    for code, name in US_STATES:
        if name.upper() == raw:
            return code
    return "NY"


def get_state_label(state_code: str) -> str:
    code = normalize_state_code(state_code)
    return STATE_LABEL_BY_CODE.get(code, code)


def _supporting_documents() -> tuple[DmvDocument, ...]:
    return (
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


def _identity_documents(*, id_code: str, state_label: str) -> tuple[DmvDocument, ...]:
    return (
        DmvDocument(
            slug="driver_license",
            code=id_code,
            name="Driver License / Non-Driver ID",
            description=f"Government photo ID for the registrant or co-registrant ({state_label}).",
            category="identity",
            upload_type="driver_license",
            tags=("id", "license"),
        ),
        DmvDocument(
            slug="insurance_id",
            code="INS",
            name="Insurance Identification Card",
            description="Proof of active liability insurance meeting state minimums.",
            category="identity",
            upload_type="insurance_id",
            tags=("insurance",),
        ),
    )


NY_DOCUMENTS: tuple[DmvDocument, ...] = (
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
) + _supporting_documents()

CT_DOCUMENTS: tuple[DmvDocument, ...] = (
    DmvDocument(
        slug="ct_h13b",
        code="H-13B",
        name="Registration & Certificate of Title Application",
        description="Primary Connecticut application for vehicle registration and title.",
        category="registration",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/H13B.pdf",
        tags=("registration", "title"),
    ),
    DmvDocument(
        slug="ct_b350",
        code="B-350",
        name="Supplemental Assignment of Ownership",
        description="Transfer ownership when the title assignment section is full or unavailable.",
        category="title",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/B350.pdf",
        tags=("transfer", "assignment"),
    ),
    DmvDocument(
        slug="ct_k208",
        code="K-208",
        name="Application for Replacement Documents",
        description="Request duplicate registration, plates, or title credentials.",
        category="registration",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/K208.pdf",
        tags=("duplicate", "replacement"),
    ),
    DmvDocument(
        slug="ct_q1",
        code="Q-1",
        name="Registration After Purchase (Sales Tax)",
        description="Sales and use tax reporting for a vehicle purchased from a dealer or private party.",
        category="tax",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/Q1.pdf",
        tags=("sales tax", "purchase"),
    ),
    DmvDocument(
        slug="ct_h31",
        code="H-31",
        name="Application for Registration Credentials",
        description="Issue or replace registration credentials and plates.",
        category="registration",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/H31.pdf",
        tags=("plates", "credentials"),
    ),
    DmvDocument(
        slug="ct_a83",
        code="A-83",
        name="Power of Attorney",
        description="Authorize a PSB or agent to sign DMV documents on the owner's behalf.",
        category="title",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/A83.pdf",
        tags=("poa", "power of attorney"),
    ),
    DmvDocument(
        slug="ct_h14",
        code="H-14",
        name="Bill of Sale",
        description="Official Connecticut bill of sale for private-party vehicle transfers.",
        category="supporting",
        dmv_url=f"{CT_FORMS_BASE}/Registration/Forms/H14.pdf",
        tags=("bill of sale", "private sale"),
    ),
) + _identity_documents(id_code="CT ID", state_label="Connecticut") + _supporting_documents()

PA_DOCUMENTS: tuple[DmvDocument, ...] = (
    DmvDocument(
        slug="pa_mv1",
        code="MV-1",
        name="Application for Certificate of Title",
        description="Primary Pennsylvania title application for purchase, transfer, or correction.",
        category="title",
        dmv_url=f"{PA_FORMS_BASE}/mv-1.pdf",
        tags=("title", "transfer"),
    ),
    DmvDocument(
        slug="pa_mv4st",
        code="MV-4ST",
        name="Application for Registration",
        description="Register a vehicle and obtain Pennsylvania registration plates.",
        category="registration",
        dmv_url=f"{PA_FORMS_BASE}/mv-4st.pdf",
        tags=("registration", "plates"),
    ),
    DmvDocument(
        slug="pa_mv41",
        code="MV-41",
        name="Temporary Registration",
        description="Short-term registration while permanent credentials are processed.",
        category="dealer",
        dmv_url=f"{PA_FORMS_BASE}/mv-41.pdf",
        tags=("temporary", "dealer"),
    ),
    DmvDocument(
        slug="pa_dl180c",
        code="DL-180C",
        name="Odometer Disclosure Statement",
        description="Federal odometer disclosure required for most title transfers.",
        category="title",
        dmv_url=f"{PA_FORMS_BASE}/dl-180c.pdf",
        tags=("odometer", "disclosure"),
    ),
    DmvDocument(
        slug="pa_mv351",
        code="MV-351",
        name="Statement of Vehicle Ownership",
        description="Affidavit supporting ownership when title evidence is incomplete.",
        category="title",
        dmv_url=f"{PA_FORMS_BASE}/mv-351.pdf",
        tags=("affidavit", "ownership"),
    ),
    DmvDocument(
        slug="pa_mv38",
        code="MV-38",
        name="Application for Duplicate Title",
        description="Request a replacement Pennsylvania certificate of title.",
        category="title",
        dmv_url=f"{PA_FORMS_BASE}/mv-38.pdf",
        tags=("duplicate", "title"),
    ),
    DmvDocument(
        slug="pa_rev1509",
        code="REV-1509",
        name="Sales Tax Exemption / Resale",
        description="Document sales tax exemption or resale status for vehicle transactions.",
        category="tax",
        dmv_url="https://www.pa.gov/content/dam/copapwp-pagov/en/revenue/documents/formsandpublications/formsforbusinesses/sut/documents/rev-1509.pdf",
        tags=("sales tax", "exemption"),
    ),
) + _identity_documents(id_code="PA ID", state_label="Pennsylvania") + _supporting_documents()

NJ_DOCUMENTS: tuple[DmvDocument, ...] = (
    DmvDocument(
        slug="nj_ba49",
        code="BA-49",
        name="Application for Certificate of Ownership",
        description="Primary New Jersey application for vehicle title and registration.",
        category="registration",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/BA-49.pdf",
        tags=("registration", "title"),
    ),
    DmvDocument(
        slug="nj_os114",
        code="OS-114",
        name="Odometer Disclosure Statement",
        description="Federal odometer disclosure for title transfers in New Jersey.",
        category="title",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/OS-114.pdf",
        tags=("odometer", "disclosure"),
    ),
    DmvDocument(
        slug="nj_os86",
        code="OS-86",
        name="Application for Duplicate Title",
        description="Request a replacement New Jersey certificate of ownership.",
        category="title",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/OS-86.pdf",
        tags=("duplicate", "title"),
    ),
    DmvDocument(
        slug="nj_os78",
        code="OS-78",
        name="Power of Attorney",
        description="Authorize a PSB or agent to sign MVC documents on the owner's behalf.",
        category="title",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/OS-78.pdf",
        tags=("poa", "power of attorney"),
    ),
    DmvDocument(
        slug="nj_os46",
        code="OS-46",
        name="Sales Tax Exemption / Resale",
        description="Document sales tax exemption for qualifying vehicle transactions.",
        category="tax",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/OS-46.pdf",
        tags=("sales tax", "exemption"),
    ),
    DmvDocument(
        slug="nj_ba64",
        code="BA-64",
        name="Rental / Lease Agreement",
        description="Lease or rental agreement supporting registration in a business name.",
        category="dealer",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/BA-64.pdf",
        tags=("lease", "rental"),
    ),
    DmvDocument(
        slug="nj_os52",
        code="OS-52",
        name="Application for Temporary Registration",
        description="Temporary registration while full MVC processing is completed.",
        category="dealer",
        dmv_url=f"{NJ_FORMS_BASE}/vehicles/OS-52.pdf",
        tags=("temporary",),
    ),
) + _identity_documents(id_code="NJ ID", state_label="New Jersey") + _supporting_documents()


def _generic_documents(state_code: str) -> tuple[DmvDocument, ...]:
    label = get_state_label(state_code)
    portal = STATE_DMV_PORTALS.get(state_code, "https://www.usa.gov/motor-vehicle-services")
    prefix = state_code.lower()
    return (
        DmvDocument(
            slug=f"{prefix}_title_app",
            code="TITLE",
            name=f"{label} Title Application",
            description=f"Official title application forms for {label}.",
            category="title",
            dmv_url=portal,
            tags=("title", "transfer"),
        ),
        DmvDocument(
            slug=f"{prefix}_reg_app",
            code="REG",
            name=f"{label} Registration Application",
            description=f"Official registration forms for {label} vehicles.",
            category="registration",
            dmv_url=portal,
            tags=("registration", "plates"),
        ),
        DmvDocument(
            slug=f"{prefix}_odometer",
            code="ODO",
            name="Odometer Disclosure Statement",
            description="Federal odometer disclosure commonly required for title transfers.",
            category="title",
            dmv_url=portal,
            tags=("odometer", "disclosure"),
        ),
        DmvDocument(
            slug=f"{prefix}_poa",
            code="POA",
            name="Power of Attorney",
            description="Authorize a PSB or agent to sign motor vehicle documents.",
            category="title",
            dmv_url=portal,
            tags=("poa", "power of attorney"),
        ),
        DmvDocument(
            slug=f"{prefix}_sales_tax",
            code="TAX",
            name="Sales / Use Tax Form",
            description=f"Sales or use tax documentation for {label} vehicle transactions.",
            category="tax",
            dmv_url=portal,
            tags=("sales tax",),
        ),
        DmvDocument(
            slug=f"{prefix}_portal",
            code="DMV",
            name=f"{label} DMV Forms Portal",
            description=f"Browse all official {label} motor vehicle forms and instructions.",
            category="registration",
            dmv_url=portal,
            tags=("forms", "portal"),
        ),
    ) + _identity_documents(id_code=f"{state_code} ID", state_label=label) + _supporting_documents()


STATE_DOCUMENT_CATALOGS: dict[str, tuple[DmvDocument, ...]] = {
    "NY": NY_DOCUMENTS,
    "CT": CT_DOCUMENTS,
    "PA": PA_DOCUMENTS,
    "NJ": NJ_DOCUMENTS,
}


def get_dmv_documents_for_state(state_code: str) -> tuple[DmvDocument, ...]:
    code = normalize_state_code(state_code)
    if code in STATE_DOCUMENT_CATALOGS:
        return STATE_DOCUMENT_CATALOGS[code]
    return _generic_documents(code)


# Backward-compatible NY export
DMV_DOCUMENTS = NY_DOCUMENTS

NY_PREFILL_FORM_MAP: dict[str, str] = {
    doc.slug: f"static/core/pdf/{doc.slug}_template.pdf"
    for doc in NY_DOCUMENTS
    if doc.prefill
}

DMV_PREFILL_FORM_MAP = NY_PREFILL_FORM_MAP
DMV_PREFILL_SLUGS = frozenset(NY_PREFILL_FORM_MAP.keys())


def get_prefill_slugs_for_state(state_code: str) -> frozenset[str]:
    if normalize_state_code(state_code) == "NY":
        return DMV_PREFILL_SLUGS
    return frozenset()


def get_prefill_form_map_for_state(state_code: str) -> dict[str, str]:
    if normalize_state_code(state_code) == "NY":
        return DMV_PREFILL_FORM_MAP
    return {}


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
    state_code: str = "NY",
) -> list[dict[str, Any]]:
    """Group state catalog entries with attachment status for the vehicle page."""
    catalog = get_dmv_documents_for_state(state_code)
    uploads = [doc for doc in documents if doc.file]

    categories: list[dict[str, Any]] = []
    for cat_id, cat_label in DMV_DOCUMENT_CATEGORIES:
        items: list[dict[str, Any]] = []
        for entry in catalog:
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

"""Virtual sections for the Core app in Django admin."""

CORE_ADMIN_GROUPS = (
    (
        "PSB & Access",
        (
            "Organization",
            "OrganizationMembership",
            "UserSession",
            "SiteNews",
        ),
    ),
    (
        "Clients & Intake",
        (
            "Client",
            "Vehicle",
            "ClientIntake",
        ),
    ),
    (
        "Services & Receipts",
        (
            "ServiceRecord",
            "ServiceAuditLog",
            "ServiceDocument",
            "CustomServiceType",
        ),
    ),
    (
        "Referrals & Partners",
        (
            "Referral",
            "ReferralPayment",
        ),
    ),
    (
        "Spaces & Documents",
        (
            "Space",
            "KnowledgeHubMaterial",
            "DocumentFolder",
            "SpaceDocumentType",
            "SpaceDocumentRecord",
        ),
    ),
    (
        "Inventory",
        (
            "InventoryCategory",
            "InventoryProduct",
            "InventoryBuyer",
            "InventoryInvoice",
            "InventoryStockMovement",
            "InventorySupplier",
            "InventoryPurchase",
            "InventoryPurchaseLine",
        ),
    ),
    (
        "Motor Club",
        (
            "MotorclubConfig",
            "MotorclubB2BPartner",
            "MotorclubMembership",
        ),
    ),
    (
        "TLC",
        (
            "TLCPolicy",
            "TLCCarrier",
            "TLCFinanceCompany",
            "TLCPolicyCancellation",
            "TLCReinstatement",
            "TLCEndorsement",
            "TLCDMVService",
            "TLCCarrierRemittance",
            "TLCPaymentTransaction",
            "TLCReceipt",
            "TLCPolicyDocument",
            "TLCPolicyTimelineEvent",
        ),
    ),
    (
        "Agent Portal",
        (
            "AgentTask",
            "AgentAttendanceSession",
            "AgentActivityEvent",
        ),
    ),
)

CORE_GROUP_ORDER = {name: index for index, (name, _) in enumerate(CORE_ADMIN_GROUPS)}

CORE_MODEL_TO_GROUP = {}
for group_name, model_names in CORE_ADMIN_GROUPS:
    for model_name in model_names:
        CORE_MODEL_TO_GROUP[model_name.lower()] = group_name


def group_core_models(models):
    """Split core model admin entries into labeled sections."""
    by_key = {model["object_name"].lower(): model for model in models}
    grouped = []
    assigned = set()

    for group_name, model_names in CORE_ADMIN_GROUPS:
        section_models = []
        for model_name in model_names:
            key = model_name.lower()
            if key in by_key:
                section_models.append(by_key[key])
                assigned.add(key)
        if section_models:
            grouped.append({"name": group_name, "models": section_models})

    remaining = [model for key, model in by_key.items() if key not in assigned]
    if remaining:
        grouped.append({"name": "Other", "models": sorted(remaining, key=lambda m: m["name"])})

    return grouped


def split_core_app_entry(app_entry):
    """Replace one Core app block with multiple grouped blocks on the admin index."""
    grouped_sections = group_core_models(app_entry["models"])
    blocks = []
    for section in grouped_sections:
        blocks.append(
            {
                "name": section["name"],
                "app_label": app_entry["app_label"],
                "app_url": app_entry["app_url"],
                "has_module_perms": app_entry["has_module_perms"],
                "models": section["models"],
            }
        )
    return blocks

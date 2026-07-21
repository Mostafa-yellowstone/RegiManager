"""Per-PSB (Organization) backup export and disaster-recovery restore.

Package layout inside the zip:
  manifest.json
  data.json
  media/<model_label>/<old_pk>/<field_name>/<filename>
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import FileField, ImageField, ManyToManyField
from django.db.models.fields.related import ForeignKey, OneToOneField
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.text import slugify

from .models import Organization

logger = logging.getLogger(__name__)
User = get_user_model()

SCHEMA_VERSION = 1

# Organization scalar fields restored onto the target row (identity tokens preserved).
ORG_RESTORE_FIELDS = (
    "name",
    "business_owner_name",
    "address_line",
    "city",
    "state",
    "phone_number",
    "email",
    "psbc_license",
    "psbc_license_effective_date",
    "psbc_license_expiration_date",
    "psbc_license_alert_days",
    "max_agents",
    "is_active",
    "is_automation_enabled",
    "is_public_intake_enabled",
    "is_public_insurance_intake_enabled",
    "insurance_intake_display_name",
    "insurance_intake_tagline",
    "insurance_ezlynx_quote_url",
    "insurance_intake_portal_mode",
    "insurance_show_review_button",
    "insurance_review_link",
    "show_review_button",
    "review_link",
)

# Models wiped/restored in dependency order (parents before children).
# Soft-delete models are queried via all_objects and hard-deleted on wipe.
EXPORT_MODELS: list[tuple[str, Callable]] = []


def _register():
    """Build EXPORT_MODELS once models are importable."""
    global EXPORT_MODELS
    if EXPORT_MODELS:
        return

    def org_fk(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            manager = getattr(model, "all_objects", model.objects)
            return manager.filter(organization=organization)

        return label, qs

    def via_client(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            manager = getattr(model, "all_objects", model.objects)
            return manager.filter(client__organization=organization)

        return label, qs

    def via_service(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(service_record__organization=organization)

        return label, qs

    def via_referral(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(referral__organization=organization)

        return label, qs

    def via_bank(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(bank_account__organization=organization)

        return label, qs

    def via_ins_company(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(insurance_company__organization=organization)

        return label, qs

    def via_space(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(space__organization=organization)

        return label, qs

    def via_product(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(product__organization=organization)

        return label, qs

    def via_invoice(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(invoice__organization=organization)

        return label, qs

    def via_purchase(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(purchase__organization=organization)

        return label, qs

    def via_tlc_policy(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(policy__organization=organization)

        return label, qs

    def via_tlc_statement(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(statement__organization=organization)

        return label, qs

    def via_tlc_txn(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(transaction__organization=organization)

        return label, qs

    def via_campaign_batch(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(campaign__organization=organization)

        return label, qs

    def sitenews_org(label: str):
        model = apps.get_model(label)

        def qs(organization: Organization):
            return model.objects.filter(organization=organization)

        return label, qs

    layers = [
        org_fk("core.customsourcetype"),
        org_fk("core.customservicetype"),
        org_fk("core.referralcategoryoption"),
        org_fk("core.insurancetypeoption"),
        org_fk("core.organizationmembership"),
        org_fk("core.referral"),
        org_fk("core.client"),
        via_client("core.vehicle"),
        via_client("core.clientnote"),
        org_fk("core.clientintake"),
        org_fk("core.servicerecord"),
        via_service("core.servicerecordpayment"),
        via_service("core.servicedocument"),
        via_service("core.serviceauditlog"),
        via_referral("core.referralpayment"),
        org_fk("core.automationlog"),
        org_fk("core.space"),
        org_fk("core.documentfolder"),
        org_fk("core.spacedocumenttype"),
        org_fk("core.spacedocumentrecord"),
        via_space("core.knowledgehubmaterial"),
        org_fk("core.inventorycategory"),
        org_fk("core.inventoryproduct"),
        org_fk("core.inventorybuyer"),
        org_fk("core.inventorysupplier"),
        org_fk("core.inventoryinvoice"),
        via_invoice("core.inventoryinvoiceline"),
        org_fk("core.inventorypurchase"),
        via_purchase("core.inventorypurchaseline"),
        via_product("core.inventorystockmovement"),
        org_fk("core.insurancecompany"),
        via_ins_company("core.insurancecompanydocument"),
        org_fk("core.insurancepolicy"),
        org_fk("core.insuranceintake"),
        org_fk("core.dailypaymenttransaction"),
        org_fk("core.bankaccount"),
        via_bank("core.banktransaction"),
        org_fk("core.motorclubconfig"),
        org_fk("core.motorclubb2bpartner"),
        org_fk("core.motorclubmembership"),
        org_fk("core.emailmarketinglist"),
        org_fk("core.emailmarketingcontact"),
        org_fk("core.emailmarketingasset"),
        org_fk("core.emailcampaign"),
        via_campaign_batch("core.emailcampaignbatch"),
        via_campaign_batch("core.emailcampaignrecipient"),
        org_fk("core.tlccarrier"),
        org_fk("core.tlcfinancecompany"),
        org_fk("core.tlccarriercommissionrule"),
        org_fk("core.tlcpolicy"),
        via_tlc_policy("core.tlcpremiumbreakdown"),
        via_tlc_policy("core.tlcinstallment"),
        via_tlc_policy("core.tlcreinstatement"),
        via_tlc_policy("core.tlcendorsement"),
        via_tlc_policy("core.tlcdmvservice"),
        via_tlc_policy("core.tlcpolicycancellation"),
        via_tlc_policy("core.tlccarrierremittance"),
        via_tlc_policy("core.tlcpolicyvehicle"),
        via_tlc_policy("core.tlcpolicydriver"),
        via_tlc_policy("core.tlcpolicydocument"),
        via_tlc_policy("core.tlcpolicytimelineevent"),
        via_tlc_policy("core.tlcpolicyfinance"),
        via_tlc_policy("core.tlcinstallmentreminder"),
        org_fk("core.tlccarrierstatement"),
        via_tlc_statement("core.tlccarrierstatementline"),
        org_fk("core.tlcpaymenttransaction"),
        via_tlc_txn("core.tlcpaymentsplit"),
        via_tlc_txn("core.tlcreceipt"),
        sitenews_org("core.sitenews"),
        org_fk("core.notification"),
    ]

    # Drop any model that isn't installed (forward-compat).
    resolved = []
    for label, collector in layers:
        try:
            apps.get_model(label)
            resolved.append((label, collector))
        except LookupError:
            logger.warning("PSB backup: skip unknown model %s", label)
    EXPORT_MODELS = resolved


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def _user_ref(user) -> dict | None:
    if not user:
        return None
    return {"_user": user.get_username()}


def _resolve_user(ref: dict | None, *, create_missing: bool = True):
    if not ref or not ref.get("_user"):
        return None
    username = ref["_user"]
    user = User.objects.filter(username=username).first()
    if user:
        return user
    if not create_missing:
        return None
    # Inactive stub so memberships/history can re-link without cloning passwords.
    return User.objects.create_user(
        username=username,
        email=f"{username}@restored.local",
        password=get_random_string(32),
        is_active=False,
    )


def _serialize_instance(obj, media_files: list[tuple[str, bytes]]) -> dict:
    model = obj.__class__
    label = model._meta.label_lower
    fields: dict[str, Any] = {}
    deferred_m2m: dict[str, list] = {}

    for field in model._meta.local_fields:
        name = field.name
        if name == "id" or name == "pk":
            continue

        if isinstance(field, (FileField, ImageField)):
            file_value = getattr(obj, name)
            if file_value and getattr(file_value, "name", None):
                try:
                    file_value.open("rb")
                    content = file_value.read()
                    file_value.close()
                except Exception:
                    logger.exception("Failed reading file %s.%s for pk=%s", label, name, obj.pk)
                    fields[name] = None
                    continue
                filename = Path(file_value.name).name
                archive_path = f"media/{label}/{obj.pk}/{name}/{filename}"
                media_files.append((archive_path, content))
                fields[name] = {"_file": archive_path, "name": filename}
            else:
                fields[name] = None
            continue

        if isinstance(field, (ForeignKey, OneToOneField)):
            raw = getattr(obj, field.attname)
            related = field.related_model
            if related == User or (related and related._meta.label_lower == "auth.user"):
                fields[name] = _user_ref(getattr(obj, name, None))
            elif related == Organization:
                fields[name] = {"_org": True}
            elif raw is None:
                fields[name] = None
            else:
                fields[name] = {
                    "_fk": related._meta.label_lower,
                    "pk": raw,
                }
            continue

        fields[name] = _json_safe(field.value_from_object(obj))

    for field in model._meta.many_to_many:
        if not field.concrete:
            continue
        related = field.related_model
        if related == Organization:
            continue
        if related and related._meta.label_lower == "auth.user":
            deferred_m2m[field.name] = [
                _user_ref(u) for u in getattr(obj, field.name).all()
            ]
        else:
            deferred_m2m[field.name] = [
                {"_fk": related._meta.label_lower, "pk": pk}
                for pk in getattr(obj, field.name).values_list("pk", flat=True)
            ]

    return {
        "model": label,
        "old_pk": obj.pk,
        "fields": fields,
        "m2m": deferred_m2m,
    }


def build_backup_payload(organization: Organization) -> tuple[dict, dict, list[tuple[str, bytes]]]:
    """Return (manifest, data, media_files)."""
    _register()
    media_files: list[tuple[str, bytes]] = []
    objects: list[dict] = []
    counts: dict[str, int] = {}

    org_fields = {}
    for name in ORG_RESTORE_FIELDS:
        if hasattr(organization, name):
            org_fields[name] = _json_safe(getattr(organization, name))
    # Logo
    if organization.logo and organization.logo.name:
        try:
            organization.logo.open("rb")
            content = organization.logo.read()
            organization.logo.close()
            filename = Path(organization.logo.name).name
            archive_path = f"media/core.organization/{organization.pk}/logo/{filename}"
            media_files.append((archive_path, content))
            org_fields["logo"] = {"_file": archive_path, "name": filename}
        except Exception:
            logger.exception("Failed reading organization logo")
            org_fields["logo"] = None
    else:
        org_fields["logo"] = None

    for label, collector in EXPORT_MODELS:
        qs = collector(organization).order_by("pk")
        rows = []
        for obj in qs.iterator(chunk_size=200):
            rows.append(_serialize_instance(obj, media_files))
        if rows:
            objects.extend(rows)
            counts[label] = len(rows)

    data = {
        "organization": {
            "source_id": organization.pk,
            "source_name": organization.name,
            "fields": org_fields,
        },
        "objects": objects,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": timezone.now().isoformat(),
        "source_organization_id": organization.pk,
        "source_organization_name": organization.name,
        "object_counts": counts,
        "object_total": len(objects),
        "media_file_count": len(media_files),
    }
    return manifest, data, media_files


def export_organization_zip(organization: Organization) -> bytes:
    """Build a backup zip in memory and return bytes."""
    manifest, data, media_files = build_backup_payload(organization)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("data.json", json.dumps(data, indent=2))
        for path, content in media_files:
            zf.writestr(path, content)
    return buffer.getvalue()


def backup_filename(organization: Organization) -> str:
    stamp = timezone.localdate().strftime("%Y%m%d")
    slug = slugify(organization.name) or f"org-{organization.pk}"
    return f"psb-backup-{slug}-{stamp}.zip"


def _hard_delete_queryset(qs):
    model = qs.model
    if hasattr(model, "hard_delete"):
        for obj in qs.iterator(chunk_size=200):
            obj.hard_delete()
    else:
        qs.delete()


@transaction.atomic
def wipe_organization_tenant_data(organization: Organization) -> dict[str, int]:
    """Delete all org-scoped rows; keep the Organization row."""
    _register()
    deleted: dict[str, int] = {}
    for label, collector in reversed(EXPORT_MODELS):
        qs = collector(organization)
        count = qs.count()
        if count:
            _hard_delete_queryset(qs)
            deleted[label] = count
    return deleted


def _parse_value(field, value: Any, id_maps: dict[str, dict[int, int]], target_org: Organization):
    if value is None:
        return None
    if isinstance(field, (FileField, ImageField)):
        return None  # applied after create via ContentFile
    if isinstance(field, (ForeignKey, OneToOneField)):
        if not isinstance(value, dict):
            return None
        if value.get("_org"):
            return target_org.pk
        if "_user" in value:
            user = _resolve_user(value)
            return user.pk if user else None
        if "_fk" in value:
            old_pk = value.get("pk")
            if old_pk is None:
                return None
            mapped = id_maps.get(value["_fk"], {}).get(old_pk)
            return mapped
        return None

    if isinstance(field, (models.DateTimeField, models.DateField, models.TimeField)):
        if value == "":
            return None
        return value
    if isinstance(field, models.DecimalField):
        if value == "" or value is None:
            return None
        return Decimal(str(value))
    if isinstance(field, models.BooleanField):
        return bool(value)
    return value


def _unique_regen_fields(model, fields: dict) -> dict:
    """Clear globally-unique identifiers so save()/DB can allocate fresh ones."""
    label = model._meta.label_lower
    out = dict(fields)
    if label == "core.servicerecord":
        out["receipt_number"] = ""
        out["case_id"] = None
    if label == "core.inventoryinvoice" and "invoice_number" in out:
        out["invoice_number"] = f"INV-R-{get_random_string(10)}"
    if label == "core.inventorypurchase" and "purchase_number" in out:
        out["purchase_number"] = f"PO-R-{get_random_string(10)}"
    if label == "core.tlcreceipt" and "receipt_number" in out:
        out["receipt_number"] = f"TLC-R-{get_random_string(10)}"
    return out


def _apply_file_field(obj, field_name: str, meta: dict | None, zip_file: zipfile.ZipFile):
    if not meta or not meta.get("_file"):
        return
    archive_path = meta["_file"]
    try:
        content = zip_file.read(archive_path)
    except KeyError:
        logger.warning("Missing media in backup: %s", archive_path)
        return
    filename = meta.get("name") or Path(archive_path).name
    getattr(obj, field_name).save(filename, ContentFile(content), save=True)


@transaction.atomic
def restore_organization_from_zip(
    target_organization: Organization,
    zip_bytes: bytes,
    *,
    confirm_name: str,
) -> dict[str, Any]:
    """Wipe target tenant data and restore from a backup zip."""
    if (confirm_name or "").strip() != target_organization.name:
        raise ValueError(
            "Confirmation text must exactly match the target PSB name "
            f"({target_organization.name!r})."
        )

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            data = json.loads(zf.read("data.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("Invalid backup: missing manifest.json or data.json") from exc

        version = manifest.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported backup schema_version={version!r}; "
                f"this server expects {SCHEMA_VERSION}."
            )

        wiped = wipe_organization_tenant_data(target_organization)

        # Restore organization profile (keep invite_code / portal_token).
        org_fields = (data.get("organization") or {}).get("fields") or {}
        for name in ORG_RESTORE_FIELDS:
            if name in org_fields and hasattr(target_organization, name):
                field = target_organization._meta.get_field(name)
                setattr(
                    target_organization,
                    name,
                    _parse_value(field, org_fields[name], {}, target_organization),
                )
        target_organization.save()
        if org_fields.get("logo"):
            _apply_file_field(target_organization, "logo", org_fields["logo"], zf)

        _register()
        id_maps: dict[str, dict[int, int]] = {}
        restored_counts: dict[str, int] = {}
        self_fk_pending: list[tuple[Any, str, dict]] = []
        m2m_pending: list[tuple[Any, dict]] = []
        file_pending: list[tuple[Any, str, dict]] = []

        objects = data.get("objects") or []
        # Group by model preserving order in EXPORT_MODELS
        order_index = {label: idx for idx, (label, _) in enumerate(EXPORT_MODELS)}
        objects.sort(key=lambda row: (order_index.get(row.get("model"), 10_000), row.get("old_pk") or 0))

        for row in objects:
            label = row["model"]
            try:
                model = apps.get_model(label)
            except LookupError:
                continue
            old_pk = row["old_pk"]
            raw_fields = _unique_regen_fields(model, row.get("fields") or {})

            create_kwargs = {}
            deferred_files = {}
            deferred_self = {}
            skip_row = False

            for field in model._meta.local_fields:
                name = field.name
                if name in ("id", "pk") or name not in raw_fields:
                    continue
                value = raw_fields[name]
                if isinstance(field, (FileField, ImageField)):
                    if value:
                        deferred_files[name] = value
                    continue
                if isinstance(field, (ForeignKey, OneToOneField)):
                    if isinstance(value, dict) and value.get("_org"):
                        create_kwargs[name] = target_organization
                        continue
                    if (
                        isinstance(value, dict)
                        and value.get("_fk") == label
                        and value.get("pk") is not None
                    ):
                        create_kwargs[field.attname] = None
                        deferred_self[name] = value
                        continue
                    related = field.related_model
                    if related == User or (
                        related and related._meta.label_lower == "auth.user"
                    ):
                        user = _resolve_user(value if isinstance(value, dict) else None)
                        if user is None and not field.null:
                            skip_row = True
                            logger.warning(
                                "Skip %s old_pk=%s: required user FK %s missing",
                                label,
                                old_pk,
                                name,
                            )
                            break
                        create_kwargs[field.attname] = user.pk if user else None
                        continue
                    parsed = _parse_value(field, value, id_maps, target_organization)
                    if parsed is None and value is not None and not field.null:
                        skip_row = True
                        logger.warning(
                            "Skip %s old_pk=%s: required FK %s not mapped (%r)",
                            label,
                            old_pk,
                            name,
                            value,
                        )
                        break
                    create_kwargs[field.attname] = parsed
                    continue
                create_kwargs[name] = _parse_value(field, value, id_maps, target_organization)

            if skip_row:
                continue

            if any(f.name == "organization" for f in model._meta.fields):
                create_kwargs["organization"] = target_organization

            try:
                obj = model(**create_kwargs)
                obj.save()
            except Exception:
                logger.exception("Failed restoring %s old_pk=%s", label, old_pk)
                raise

            id_maps.setdefault(label, {})[old_pk] = obj.pk
            restored_counts[label] = restored_counts.get(label, 0) + 1

            for fname, meta in deferred_files.items():
                file_pending.append((obj, fname, meta))
            for fname, ref in deferred_self.items():
                self_fk_pending.append((obj, fname, ref))
            if row.get("m2m"):
                m2m_pending.append((obj, row["m2m"]))

        # Patch self-FKs
        for obj, fname, ref in self_fk_pending:
            new_pk = id_maps.get(ref["_fk"], {}).get(ref["pk"])
            if new_pk:
                setattr(obj, f"{fname}_id", new_pk)
                obj.save(update_fields=[fname])

        # Files
        for obj, fname, meta in file_pending:
            _apply_file_field(obj, fname, meta, zf)

        # M2M
        for obj, m2m_data in m2m_pending:
            for fname, refs in m2m_data.items():
                if not hasattr(obj, fname):
                    continue
                manager = getattr(obj, fname)
                ids = []
                for ref in refs or []:
                    if not isinstance(ref, dict):
                        continue
                    if "_user" in ref:
                        user = _resolve_user(ref)
                        if user:
                            ids.append(user.pk)
                    elif "_fk" in ref:
                        mapped = id_maps.get(ref["_fk"], {}).get(ref["pk"])
                        if mapped:
                            ids.append(mapped)
                if ids:
                    manager.set(ids)

    return {
        "wiped": wiped,
        "restored": restored_counts,
        "source_organization_name": manifest.get("source_organization_name"),
        "exported_at": manifest.get("exported_at"),
        "target_organization_id": target_organization.pk,
        "target_organization_name": target_organization.name,
    }


def read_manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))

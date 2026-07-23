"""Companion serialization helpers for TLC, inventory, documents, and knowledge spaces."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, F, Q
from django.utils import timezone

from .inventory_crm import inventory_dashboard_stats
from .models import (
    DocumentFolder,
    InventoryProduct,
    KnowledgeHubMaterial,
    SpaceDocumentRecord,
    SpaceDocumentType,
)
from .tlc_models import TLCPolicy
from .tlc_profitability import tlc_dashboard_stats


def _money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def _user_label(user) -> str | None:
    if not user:
        return None
    return user.get_full_name().strip() or user.username


# ── TLC ──────────────────────────────────────────────────────────────────────


def build_tlc_owner_summary(space, *, today=None) -> dict:
    stats = tlc_dashboard_stats(space, today=today)
    return {
        "total_policies": stats["total_policies"],
        "active_policies": stats["active_policies"],
        "pending_policies": stats["pending_policies"],
        "cancelled_policies": stats["cancelled_policies"],
        "month_new_policies": stats["month_new_policies"],
        "aggregate_net_profit": _money(stats["aggregate_net_profit"]),
        "aggregate_gross_revenue": _money(stats["aggregate_gross_revenue"]),
        "policies_analyzed": stats["policies_analyzed"],
    }


def serialize_tlc_policy(policy: TLCPolicy) -> dict:
    return {
        "id": policy.id,
        "policy_number": policy.policy_number,
        "named_insured": policy.named_insured or policy.business_name or "",
        "carrier": policy.carrier or "",
        "status": policy.status,
        "policy_type": policy.policy_type,
        "plate_number": policy.plate_number or "",
        "effective_date": policy.effective_date.isoformat() if policy.effective_date else None,
        "expiration_date": policy.expiration_date.isoformat() if policy.expiration_date else None,
        "broker_name": policy.broker_name or "",
        "added_by": _user_label(policy.producer) or _user_label(policy.csr),
    }


def list_tlc_policies_for_org(
    organization,
    *,
    status: str | None = None,
    limit: int = 50,
):
    qs = (
        TLCPolicy.objects.filter(organization=organization)
        .select_related("producer", "csr")
        .order_by("-created_at")
    )
    if status == "cancelled":
        qs = qs.filter(status__in=[TLCPolicy.Status.CANCELLED, TLCPolicy.Status.SUSPENDED])
    elif status:
        qs = qs.filter(status=status)
    return [serialize_tlc_policy(p) for p in qs[:limit]]


# ── Inventory (Custom Inventory / Kimo's Bikes book) ──────────────────────────


def _reorder_status(product: InventoryProduct) -> str:
    if product.quantity <= 0:
        return "Out of Stock"
    if product.quantity <= product.low_stock_threshold:
        return "Low Stock"
    return "Normal"


def build_inventory_owner_summary(space) -> dict:
    stats = inventory_dashboard_stats(space)
    return {
        "total_products": stats["total_products"],
        "total_units": stats["total_units"],
        "inventory_value": _money(stats["total_inventory_value"]),
        "low_stock_count": stats["low_stock_count"],
        "sales_today_total": _money(stats["sales_today_total"]),
        "sales_today_count": stats["sales_today_count"],
        "sales_month_total": _money(stats["sales_month_total"]),
        "sales_month_count": stats["sales_month_count"],
        "category_count": stats["category_count"],
        "buyer_count": stats["buyer_count"],
        "invoice_count": stats["invoice_count"],
        "supplier_count": stats["supplier_count"],
    }


def serialize_inventory_product(product: InventoryProduct) -> dict:
    return {
        "id": product.id,
        "item_name": product.name,
        "sku": product.sku or "",
        "stock_count": product.quantity,
        "unit_price": _money(product.unit_price),
        "reorder_status": _reorder_status(product),
        "category": product.category.name if product.category_id else "",
        "low_stock_threshold": product.low_stock_threshold,
        "is_active": product.is_active,
    }


def list_inventory_products_for_org(
    organization,
    *,
    stock_status: str | None = None,
    limit: int = 50,
):
    qs = (
        InventoryProduct.objects.filter(organization=organization, is_active=True)
        .select_related("category")
        .order_by("name")
    )
    if stock_status == "out_of_stock":
        qs = qs.filter(quantity__lte=0)
    elif stock_status == "low_stock":
        qs = qs.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold"))
    elif stock_status == "normal":
        qs = qs.filter(quantity__gt=F("low_stock_threshold"))
    return [serialize_inventory_product(p) for p in qs[:limit]]


# ── Documents ────────────────────────────────────────────────────────────────


def build_documents_owner_summary(space) -> dict:
    records = SpaceDocumentRecord.objects.filter(space=space)
    return {
        "total_records": records.count(),
        "folder_count": DocumentFolder.objects.filter(space=space).count(),
        "type_count": SpaceDocumentType.objects.filter(space=space).count(),
        "month_new_records": records.filter(
            created_at__date__gte=timezone.localdate().replace(day=1)
        ).count(),
    }


def serialize_document_record(record: SpaceDocumentRecord) -> dict:
    doc_type = record.document_type.name if record.document_type_id else ""
    folder = record.folder.name if record.folder_id else ""
    return {
        "id": record.id,
        "doc_name": record.record_number or record.order_number or f"DOC-{record.id}",
        "doc_type": doc_type,
        "status": folder or "Filed",
        "file_size": f"{record.quantity} units" if record.quantity else "",
        "uploaded_date": record.created_at.date().isoformat() if record.created_at else "",
        "client_name": record.order_number or "",
        "record_number": record.record_number or "",
        "order_number": record.order_number or "",
        "folder": folder,
        "quantity": record.quantity,
        "added_by": _user_label(record.added_by),
    }


def list_document_records_for_org(
    organization,
    *,
    doc_type: str | None = None,
    limit: int = 50,
):
    qs = (
        SpaceDocumentRecord.objects.filter(organization=organization)
        .select_related("document_type", "folder", "added_by")
        .order_by("-created_at")
    )
    if doc_type:
        qs = qs.filter(Q(document_type__name__iexact=doc_type))
    return [serialize_document_record(r) for r in qs[:limit]]


# ── Knowledge Hub ────────────────────────────────────────────────────────────


def build_knowledge_owner_summary(space) -> dict:
    materials = KnowledgeHubMaterial.objects.filter(space=space)
    roadmaps = (
        materials.values("roadmap_name")
        .annotate(count=Count("id"))
        .order_by("roadmap_name")
    )
    return {
        "total_materials": materials.count(),
        "roadmap_count": roadmaps.count(),
        "top_level_count": materials.filter(parent__isnull=True).count(),
        "roadmaps": [
            {"name": row["roadmap_name"], "count": row["count"]} for row in roadmaps[:12]
        ],
    }


def serialize_knowledge_material(material: KnowledgeHubMaterial) -> dict:
    return {
        "id": material.id,
        "title": material.title,
        "category": material.roadmap_name,
        "summary": (material.description or "")[:280],
        "read_time_minutes": max(1, material.step_number),
        "content_markdown": material.description or "",
        "roadmap_name": material.roadmap_name,
        "step_number": material.step_number,
        "external_url": material.external_url or "",
        "has_file": bool(material.file),
    }


def list_knowledge_materials_for_org(
    organization,
    *,
    roadmap: str | None = None,
    limit: int = 50,
):
    qs = (
        KnowledgeHubMaterial.objects.filter(space__organization=organization)
        .order_by("roadmap_name", "step_number", "created_at")
    )
    if roadmap:
        qs = qs.filter(roadmap_name__iexact=roadmap)
    return [serialize_knowledge_material(m) for m in qs[:limit]]
